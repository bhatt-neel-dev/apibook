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


class JobHeartbeatTests(DjangoTestCase):
    """Heartbeat recording + the /health/jobs freshness logic."""

    def test_cycle_records_heartbeat(self):
        from unittest.mock import MagicMock, patch

        from apps.projects.anomaly import HEARTBEAT_NAME, run_detection_cycle
        from apps.projects.models import JobHeartbeat

        client = MagicMock()
        client.execute.return_value = []
        with patch("core.database.clickhouse.client.get_clickhouse_client", return_value=client):
            run_detection_cycle()

        hb = JobHeartbeat.objects.get(name=HEARTBEAT_NAME)
        self.assertIsNotNone(hb.last_run_at)

    def test_job_health_never_ran_is_stale_only_when_enabled(self):
        import os
        from unittest.mock import patch

        from apps.projects.anomaly import job_health

        health = job_health()
        self.assertIsNone(health["last_run_at"])
        self.assertTrue(health["stale"])  # enabled + never ran = a problem

        with patch.dict(os.environ, {"APILENS_ANOMALY_ALERTS": "false"}):
            health = job_health()
            self.assertFalse(health["stale"])  # intentionally off = not a problem

    def test_job_health_staleness_threshold(self):
        from datetime import datetime, timedelta, timezone as tz

        from apps.projects.anomaly import (
            HEARTBEAT_NAME,
            HEARTBEAT_STALE_AFTER_SECONDS,
            job_health,
        )
        from apps.projects.models import JobHeartbeat

        JobHeartbeat.objects.create(
            name=HEARTBEAT_NAME,
            last_run_at=datetime.now(tz.utc) - timedelta(seconds=HEARTBEAT_STALE_AFTER_SECONDS - 60),
        )
        self.assertFalse(job_health()["stale"])  # just inside the window

        JobHeartbeat.objects.filter(name=HEARTBEAT_NAME).update(
            last_run_at=datetime.now(tz.utc) - timedelta(seconds=HEARTBEAT_STALE_AFTER_SECONDS + 60)
        )
        self.assertTrue(job_health()["stale"])  # just past it

    def test_disabled_cycle_does_not_touch_heartbeat(self):
        import os
        from unittest.mock import patch

        from apps.projects.anomaly import run_detection_cycle
        from apps.projects.models import JobHeartbeat

        with patch.dict(os.environ, {"APILENS_ANOMALY_ALERTS": "0"}):
            run_detection_cycle()

        self.assertFalse(JobHeartbeat.objects.exists())


class FalsePositiveMetricTests(DjangoTestCase):
    """viewed_at semantics + the dismissed-without-view guardrail math."""

    @classmethod
    def setUpTestData(cls):
        from apps.projects.models import App, Project
        from apps.users.models import User

        cls.user = User.objects.create(email="fp-tester@apilens.local")
        cls.project = Project.objects.create(owner=cls.user, name="FP P", slug="fp-p")
        cls.app = App.objects.create(project=cls.project, name="Api", slug="api")

    def _alert(self, dedup_suffix: str, **overrides):
        from datetime import datetime, timezone as tz

        from apps.projects.models import AlertEvent

        now = datetime.now(tz.utc)
        defaults = {
            "project": self.project,
            "app": self.app,
            "kind": "error_rate",
            "method": "GET",
            "path": f"/v1/{dedup_suffix}",
            "observed_value": 50.0,
            "baseline_value": 2.0,
            "threshold_value": 8.0,
            "window_start": now,
            "window_end": now,
            "dedup_key": f"error_rate:GET:/v1/{dedup_suffix}:{now.date().isoformat()}",
        }
        defaults.update(overrides)
        return AlertEvent.objects.create(**defaults)

    def test_first_view_wins_and_is_never_overwritten(self):
        from datetime import datetime, timedelta, timezone as tz

        from apps.projects.models import AlertEvent

        alert = self._alert("orders")
        first = datetime.now(tz.utc) - timedelta(hours=1)
        AlertEvent.objects.filter(id=alert.id, viewed_at__isnull=True).update(viewed_at=first)
        # A second "seen" uses the same guarded update — must be a no-op.
        AlertEvent.objects.filter(id=alert.id, viewed_at__isnull=True).update(
            viewed_at=datetime.now(tz.utc)
        )
        alert.refresh_from_db()
        self.assertEqual(alert.viewed_at, first)

    def test_fp_rate_counts_only_dismissed_without_view(self):
        from datetime import datetime, timezone as tz

        from apps.projects.models import AlertEvent

        now = datetime.now(tz.utc)
        # dismissed + viewed  -> investigated, NOT a false positive
        self._alert("a", status=AlertEvent.Status.DISMISSED, viewed_at=now, dismissed_at=now)
        # dismissed + never viewed -> the FP proxy
        self._alert("b", status=AlertEvent.Status.DISMISSED, dismissed_at=now)
        # still active -> not resolved, out of the denominator
        self._alert("c")

        window = AlertEvent.objects.filter(project=self.project)
        dismissed = window.filter(status=AlertEvent.Status.DISMISSED)
        self.assertEqual(dismissed.count(), 2)
        self.assertEqual(dismissed.filter(viewed_at__isnull=True).count(), 1)
        # 1 of 2 dismissed lacked a view -> 50% FP proxy rate
        self.assertEqual(
            dismissed.filter(viewed_at__isnull=True).count() / dismissed.count(), 0.5
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
