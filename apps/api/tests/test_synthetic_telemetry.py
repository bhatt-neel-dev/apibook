from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
loaded_apps = sys.modules.get("apps")
loaded_apps_file = str(getattr(loaded_apps, "__file__", "") or "")
loaded_apps_paths = [str(path) for path in getattr(loaded_apps, "__path__", [])] if loaded_apps is not None else []
api_apps_path = str(API_ROOT / "apps")
if loaded_apps is not None and (
    (loaded_apps_file and not loaded_apps_file.startswith(str(API_ROOT)))
    or (loaded_apps_paths and api_apps_path not in loaded_apps_paths)
):
    del sys.modules["apps"]

from apps.projects.synthetic.accelerators import RandomPlanner
from apps.projects.synthetic.catalog import SCENARIOS, expand_scenario_keys
from apps.projects.synthetic.generator import SyntheticRunConfig, SyntheticTelemetryEngine
from apps.projects.synthetic.validation import (
    validate_count_and_days,
    validate_selected_scenarios,
)
from apps.projects.synthetic.writers import JsonlWriter


class SyntheticTelemetryTests(unittest.TestCase):
    def test_catalog_has_required_scenario_breadth(self) -> None:
        self.assertGreaterEqual(len(SCENARIOS), 5)
        for key in (
            "api_product_growth",
            "ecommerce_checkout",
            "fintech_payments",
            "healthtech_patient",
            "logistics_fleet",
            "ai_platform",
            "telco_iot",
            "internal_saas",
            "enterprise_governance",
        ):
            self.assertIn(key, SCENARIOS)
            self.assertGreaterEqual(len(SCENARIOS[key].apps), 1)
            self.assertGreaterEqual(len(SCENARIOS[key].endpoints), 5)
            self.assertGreaterEqual(len(SCENARIOS[key].consumers), 5)

    def test_expand_all_scenarios(self) -> None:
        self.assertEqual(tuple(SCENARIOS), expand_scenario_keys(("all",)))

    def test_api_scenario_selection_requires_at_least_one_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one synthetic scenario"):
            validate_selected_scenarios([])
        with self.assertRaisesRegex(ValueError, "At least one synthetic scenario"):
            validate_selected_scenarios(["", "   "])
        self.assertEqual(("ai_platform",), validate_selected_scenarios([" AI_PLATFORM "]))

    def test_synthetic_count_and_days_validation_rejects_invalid_values(self) -> None:
        for count, days in ((0, 1), (-1, 1), (1, 0), (1, -5)):
            with self.subTest(count=count, days=days):
                with self.assertRaises(ValueError):
                    validate_count_and_days(count=count, days=days)

        with self.assertRaisesRegex(ValueError, "count must be at most 50"):
            validate_count_and_days(count=51, days=1, max_count=50)
        with self.assertRaisesRegex(ValueError, "days must be at most 7"):
            validate_count_and_days(count=1, days=8, max_days=7)
        self.assertEqual((10, 3), validate_count_and_days(count=10, days=3))

    def test_fixed_seed_is_repeatable(self) -> None:
        config = SyntheticRunConfig(
            scenario_keys=("ai_platform",),
            count=30,
            days=3,
            now=datetime(2026, 7, 3, 10, tzinfo=timezone.utc),
            seed=4242,
            accelerator="cpu",
            project_slug="qa",
        )
        first = SyntheticTelemetryEngine(config).generate()
        second = SyntheticTelemetryEngine(config).generate()
        self.assertEqual([row.as_ingest_dict() for row in first.requests], [row.as_ingest_dict() for row in second.requests])
        self.assertEqual([row.as_ingest_dict() for row in first.spans], [row.as_ingest_dict() for row in second.spans])

    def test_default_seed_rotates_by_hour(self) -> None:
        first = SyntheticTelemetryEngine(
            SyntheticRunConfig(
                scenario_keys=("fintech_payments",),
                count=5,
                now=datetime(2026, 7, 3, 10, tzinfo=timezone.utc),
                accelerator="cpu",
            )
        ).generate()
        second = SyntheticTelemetryEngine(
            SyntheticRunConfig(
                scenario_keys=("fintech_payments",),
                count=5,
                now=datetime(2026, 7, 3, 11, tzinfo=timezone.utc),
                accelerator="cpu",
            )
        ).generate()
        self.assertNotEqual(first.seed, second.seed)
        self.assertNotEqual([row.trace_id for row in first.requests], [row.trace_id for row in second.requests])

    def test_requests_logs_and_spans_are_correlated(self) -> None:
        result = SyntheticTelemetryEngine(
            SyntheticRunConfig(
                scenario_keys=("ecommerce_checkout",),
                count=120,
                days=7,
                seed=99,
                accelerator="cpu",
                project_slug="qa",
            )
        ).generate()

        self.assertEqual(120, len(result.requests))
        self.assertGreater(len(result.logs), 0)
        self.assertGreaterEqual(len(result.spans), len(result.requests))

        request_trace_ids = {event.trace_id for event in result.requests}
        request_server_span_ids = {event.span_id for event in result.requests}
        server_span_ids = {event.span_id for event in result.spans if event.parent_span_id == ""}

        self.assertTrue({event.trace_id for event in result.logs}.issubset(request_trace_ids))
        self.assertTrue({event.trace_id for event in result.spans}.issubset(request_trace_ids))
        self.assertTrue(request_server_span_ids.issubset(server_span_ids))

    def test_cpu_random_planner_reports_cpu_backend(self) -> None:
        streams = RandomPlanner("cpu").plan(count=3, seed=7)
        self.assertEqual("cpu-random", streams.backend)
        self.assertFalse(streams.used_gpu)
        self.assertEqual(3, len(streams.status_roll))

    def test_jsonl_writer_outputs_manifest_and_rows(self) -> None:
        result = SyntheticTelemetryEngine(
            SyntheticRunConfig(
                scenario_keys=("internal_saas",),
                count=15,
                seed=123,
                accelerator="cpu",
                project_slug="qa",
            )
        ).generate()
        with tempfile.TemporaryDirectory() as tmp:
            summary = JsonlWriter(tmp).write(result)
            self.assertEqual("jsonl", summary.mode)
            self.assertEqual(15, summary.requests)
            manifest = json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(15, manifest["requests"])
            request_lines = (Path(tmp) / "requests.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(15, len(request_lines))
            first = json.loads(request_lines[0])
            self.assertIn("trace_id", first)
            self.assertEqual("qa", first["project_slug"])


if __name__ == "__main__":
    unittest.main()
