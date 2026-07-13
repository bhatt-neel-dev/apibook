import sys
from datetime import datetime, timezone as tz
from unittest import TestCase
from unittest.mock import patch, MagicMock
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from apps.projects.services import AnalyticsService


class GetProjectEndpointStatsTests(TestCase):
    """
    Regression coverage for the bug where the Traffic page's endpoint table
    showed "No endpoint activity" for every project: get_project_endpoint_stats
    used to merge ClickHouse aggregates against Postgres Endpoint rows, and
    nothing in the live app can ever create one. The fixed version returns the
    ClickHouse aggregation directly, with no Postgres round-trip.
    """

    def _mock_client(self, count_rows, main_rows):
        client = MagicMock()
        client.execute.side_effect = [count_rows, main_rows]
        return client

    @patch("apps.projects.models.App.objects")
    @patch("core.database.clickhouse.client.get_clickhouse_client")
    def test_returns_clickhouse_rows_without_matching_postgres_endpoint(self, mock_get_client, mock_app_objects):
        clickhouse_rows = [
            {
                "method": "GET",
                "path": "/orders",
                "total_requests": 42,
                "error_count": 1,
                "error_rate": 2.38,
                "avg_response_time_ms": 120.5,
                "p95_response_time_ms": 300.0,
                "total_request_bytes": 1024,
                "total_response_bytes": 4096,
            }
        ]
        mock_get_client.return_value = self._mock_client(
            count_rows=[{"count()": 1}], main_rows=clickhouse_rows
        )

        result = AnalyticsService.get_project_endpoint_stats(project_id="proj-1")

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["items"], clickhouse_rows)
        # The old Postgres-merge path resolved app slugs via App.objects; the
        # fixed query only touches App.objects when an explicit `filter` rich
        # filter is passed (it isn't here), so it must never be called.
        mock_app_objects.filter.assert_not_called()

    @patch("core.database.clickhouse.client.get_clickhouse_client")
    def test_data_transfer_columns_are_selected(self, mock_get_client):
        mock_client = self._mock_client(count_rows=[{"count()": 0}], main_rows=[])
        mock_get_client.return_value = mock_client

        AnalyticsService.get_project_endpoint_stats(project_id="proj-1")

        main_query = mock_client.execute.call_args_list[1].args[0]
        self.assertIn("total_request_bytes", main_query)
        self.assertIn("total_response_bytes", main_query)

    @patch("core.database.clickhouse.client.get_clickhouse_client")
    def test_clickhouse_failure_returns_empty_result_not_an_exception(self, mock_get_client):
        mock_get_client.side_effect = Exception("connection refused")

        result = AnalyticsService.get_project_endpoint_stats(project_id="proj-1")

        self.assertEqual(result, {"items": [], "total_count": 0})


class GetProjectEndpointTimeseriesTests(TestCase):
    """
    Regression coverage for the field-naming fix: the project-level endpoint
    timeseries used to only return `error_count`, forcing the frontend to
    derive a success count client-side. It now matches the project-wide
    timeseries convention (success_count / client_error_count / server_error_count).
    """

    @patch("core.database.clickhouse.client.get_clickhouse_client")
    def test_returns_success_and_split_error_counts(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.execute.return_value = [
            {
                "bucket": datetime(2026, 7, 5, 0, 0, 0, tzinfo=tz.utc),
                "total_requests": 10,
                "success_count": 7,
                "client_error_count": 2,
                "server_error_count": 1,
                "error_count": 3,
                "avg_response_time_ms": 100.0,
                "p50_response_time_ms": 90.0,
                "p95_response_time_ms": 200.0,
                "p99_response_time_ms": 250.0,
                "total_request_bytes": 512,
                "total_response_bytes": 2048,
            }
        ]
        mock_get_client.return_value = mock_client

        rows = AnalyticsService.get_project_endpoint_timeseries(
            project_id="proj-1", method="GET", path="/orders"
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["success_count"], 7)
        self.assertEqual(row["client_error_count"], 2)
        self.assertEqual(row["server_error_count"], 1)

    @patch("core.database.clickhouse.client.get_clickhouse_client")
    def test_query_selects_split_status_class_counts(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.execute.return_value = []
        mock_get_client.return_value = mock_client

        AnalyticsService.get_project_endpoint_timeseries(
            project_id="proj-1", method="GET", path="/orders"
        )

        query = mock_client.execute.call_args.args[0]
        self.assertIn("success_count", query)
        self.assertIn("client_error_count", query)
        self.assertIn("server_error_count", query)


if __name__ == "__main__":
    import unittest

    unittest.main()
