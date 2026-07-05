import sys
from unittest import TestCase
from pathlib import Path

from django.test import TestCase as DjangoTestCase

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from apps.projects.anomaly import (
    CONSECUTIVE_WINDOWS,
    MAD_FLOOR,
    MIN_BASELINE_SAMPLES,
    anomaly_alerts_enabled,
    evaluate_metric,
    mad,
    median,
)


class MedianMadTests(TestCase):
    def test_median_odd_and_even(self):
        self.assertEqual(median([3.0, 1.0, 2.0]), 2.0)
        self.assertEqual(median([1.0, 2.0, 3.0, 4.0]), 2.5)

    def test_median_empty_raises(self):
        with self.assertRaises(ValueError):
            median([])

    def test_mad_is_outlier_resistant(self):
        values = [10.0] * 20 + [1000.0]  # one wild outlier
        med = median(values)
        self.assertEqual(med, 10.0)
        self.assertEqual(mad(values, med), 0.0)  # median deviation ignores the outlier


class EvaluateMetricTests(TestCase):
    """The decision function: alert only on sustained, baseline-relative deviation."""

    def _baseline(self, value: float, n: int = 24) -> list[float]:
        return [value] * n

    def test_flat_traffic_never_alerts(self):
        verdict = evaluate_metric([2.0, 2.0, 2.0], self._baseline(2.0), "error_rate")
        self.assertIsNone(verdict)

    def test_sustained_spike_alerts(self):
        # Baseline ~2% errors; three consecutive windows at 40% is unambiguous.
        verdict = evaluate_metric([40.0, 45.0, 42.0], self._baseline(2.0), "error_rate")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.baseline, 2.0)
        self.assertEqual(verdict.observed, 45.0)

    def test_single_window_blip_does_not_alert(self):
        # Only the middle window spikes — not sustained, must stay quiet.
        verdict = evaluate_metric([2.0, 60.0, 2.0], self._baseline(2.0), "error_rate")
        self.assertIsNone(verdict)

    def test_insufficient_current_windows_never_alerts(self):
        verdict = evaluate_metric([90.0] * (CONSECUTIVE_WINDOWS - 1), self._baseline(2.0), "error_rate")
        self.assertIsNone(verdict)

    def test_insufficient_baseline_never_alerts(self):
        # A brand-new endpoint (2 history buckets) must yield "no baseline yet",
        # not an alert against a guess.
        verdict = evaluate_metric([90.0, 90.0, 90.0], [2.0] * (MIN_BASELINE_SAMPLES - 1), "error_rate")
        self.assertIsNone(verdict)

    def test_mad_floor_prevents_hair_trigger_on_flat_baseline(self):
        # Perfectly flat baseline -> MAD 0. Without the floor, ANY deviation
        # would alert; with the error_rate floor of 2.0 points, threshold is
        # 2 + 3*2 = 8, so a drift to 5% stays quiet.
        verdict = evaluate_metric([5.0, 5.0, 5.0], self._baseline(2.0), "error_rate")
        self.assertIsNone(verdict)
        # ...but 9% (just past the floored threshold) alerts.
        verdict = evaluate_metric([9.0, 9.0, 9.0], self._baseline(2.0), "error_rate")
        self.assertIsNotNone(verdict)

    def test_latency_kind_uses_latency_floor(self):
        # Flat 100ms baseline; latency MAD floor is 15ms -> threshold 145ms.
        verdict = evaluate_metric([130.0, 130.0, 130.0], self._baseline(100.0), "latency")
        self.assertIsNone(verdict)
        verdict = evaluate_metric([150.0, 155.0, 160.0], self._baseline(100.0), "latency")
        self.assertIsNotNone(verdict)
        self.assertAlmostEqual(verdict.threshold, 100.0 + 3 * MAD_FLOOR["latency"])

    def test_noisy_baseline_widens_threshold(self):
        # A naturally spiky endpoint (alternating 0/20% errors) has a wide MAD;
        # values that would alert on a flat baseline stay quiet here.
        noisy = [0.0, 20.0] * 12
        verdict = evaluate_metric([25.0, 25.0, 25.0], noisy, "error_rate")
        self.assertIsNone(verdict)  # median 10, MAD 10 -> threshold 40

    def test_uses_only_the_last_consecutive_windows(self):
        # Old windows beyond the last CONSECUTIVE_WINDOWS are ignored.
        verdict = evaluate_metric([2.0, 2.0, 50.0, 55.0, 52.0], self._baseline(2.0), "error_rate")
        self.assertIsNotNone(verdict)


class KillSwitchTests(TestCase):
    """APILENS_ANOMALY_ALERTS follows the APILENS_CAPTURE_SPANS pattern:
    unset -> enabled; explicitly falsey env -> disabled; env can only turn OFF."""

    def setUp(self):
        import os
        self._saved = os.environ.pop("APILENS_ANOMALY_ALERTS", None)

    def tearDown(self):
        import os
        if self._saved is not None:
            os.environ["APILENS_ANOMALY_ALERTS"] = self._saved
        else:
            os.environ.pop("APILENS_ANOMALY_ALERTS", None)

    def test_enabled_when_unset(self):
        self.assertTrue(anomaly_alerts_enabled())

    def test_disabled_by_falsey_values(self):
        import os
        for value in ["0", "false", "False", "no", "off", "disabled", "", "  FALSE  "]:
            os.environ["APILENS_ANOMALY_ALERTS"] = value
            self.assertFalse(anomaly_alerts_enabled(), f"expected disabled for {value!r}")

    def test_enabled_by_truthy_values(self):
        import os
        for value in ["1", "true", "yes", "on", "anything-else"]:
            os.environ["APILENS_ANOMALY_ALERTS"] = value
            self.assertTrue(anomaly_alerts_enabled(), f"expected enabled for {value!r}")


class DetectProjectAnomaliesTests(DjangoTestCase):
    """The write path: real ORM (test DB), mocked ClickHouse."""

    @classmethod
    def setUpTestData(cls):
        from apps.projects.models import App, Project
        from apps.users.models import User

        cls.user = User.objects.create(email="anomaly-tester@apilens.local")
        cls.project = Project.objects.create(owner=cls.user, name="Anomaly P", slug="anomaly-p")
        cls.app = App.objects.create(project=cls.project, name="Checkout", slug="checkout")

    def _row(self, bucket_index: int, error_rate: float, p95: float) -> dict:
        from datetime import datetime, timedelta, timezone as tz

        return {
            "app_id": str(self.app.id),
            "method": "POST",
            "path": "/v1/checkout",
            "bucket": datetime.now(tz.utc) - timedelta(minutes=5 * bucket_index),
            "total_requests": 15,
            "error_rate": error_rate,
            "p95_response_time_ms": p95,
        }

    def _mock_client(self, current_rows, baseline_rows):
        from unittest.mock import MagicMock

        client = MagicMock()
        client.execute.side_effect = [current_rows, baseline_rows]
        return client

    def test_spike_writes_alert_with_app_mapping_and_values(self):
        from unittest.mock import patch

        from apps.projects.anomaly import detect_project_anomalies
        from apps.projects.models import AlertEvent

        current = [self._row(i, error_rate=50.0, p95=100.0) for i in range(3)]
        baseline = [self._row(i + 10, error_rate=2.0, p95=100.0) for i in range(24)]

        with patch("core.database.clickhouse.client.get_clickhouse_client") as m:
            m.return_value = self._mock_client(current, baseline)
            created = detect_project_anomalies(self.project)

        self.assertEqual(created, 1)  # error_rate only; latency is flat
        alert = AlertEvent.objects.get(project=self.project)
        self.assertEqual(alert.kind, "error_rate")
        self.assertEqual(alert.app_id, self.app.id)
        self.assertEqual(alert.method, "POST")
        self.assertEqual(alert.path, "/v1/checkout")
        self.assertEqual(alert.observed_value, 50.0)
        self.assertEqual(alert.baseline_value, 2.0)
        self.assertEqual(alert.status, AlertEvent.Status.ACTIVE)

    def test_second_cycle_same_day_is_deduped(self):
        from unittest.mock import patch

        from apps.projects.anomaly import detect_project_anomalies
        from apps.projects.models import AlertEvent

        current = [self._row(i, error_rate=50.0, p95=100.0) for i in range(3)]
        baseline = [self._row(i + 10, error_rate=2.0, p95=100.0) for i in range(24)]

        with patch("core.database.clickhouse.client.get_clickhouse_client") as m:
            m.return_value = self._mock_client(current, baseline)
            first = detect_project_anomalies(self.project)
            m.return_value = self._mock_client(current, baseline)
            second = detect_project_anomalies(self.project)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(AlertEvent.objects.filter(project=self.project).count(), 1)

    def test_endpoint_without_baseline_never_alerts(self):
        from unittest.mock import patch

        from apps.projects.anomaly import detect_project_anomalies
        from apps.projects.models import AlertEvent

        current = [self._row(i, error_rate=90.0, p95=900.0) for i in range(3)]

        with patch("core.database.clickhouse.client.get_clickhouse_client") as m:
            m.return_value = self._mock_client(current, [])  # brand-new endpoint
            created = detect_project_anomalies(self.project)

        self.assertEqual(created, 0)
        self.assertFalse(AlertEvent.objects.filter(project=self.project).exists())

    def test_empty_current_traffic_short_circuits(self):
        from unittest.mock import MagicMock, patch

        from apps.projects.anomaly import detect_project_anomalies

        client = MagicMock()
        client.execute.return_value = []
        with patch("core.database.clickhouse.client.get_clickhouse_client") as m:
            m.return_value = client
            created = detect_project_anomalies(self.project)

        self.assertEqual(created, 0)
        # Only the current-windows query ran; no baseline query for dead projects.
        self.assertEqual(client.execute.call_count, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
