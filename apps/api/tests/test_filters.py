import sys
from unittest import TestCase
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from apps.projects.filters import build_where, parse_filter


class RichFilterTests(TestCase):
    def test_status_class_not_negates_status_range(self) -> None:
        params = {}

        where = build_where(parse_filter("status_class:not:2xx"), params)

        self.assertIn("NOT", where)
        self.assertIn("status_code >=", where)
        self.assertIn("status_code <", where)
        self.assertEqual(params["flt0_0_lo"], 200)
        self.assertEqual(params["flt0_0_hi"], 300)

    def test_status_class_is_keeps_positive_status_range(self) -> None:
        params = {}

        where = build_where(parse_filter("status_class:is:2xx"), params)

        self.assertNotIn("NOT", where)
        self.assertIn("status_code >=", where)
        self.assertIn("status_code <", where)
        self.assertEqual(params["flt0_0_lo"], 200)
        self.assertEqual(params["flt0_0_hi"], 300)


if __name__ == "__main__":
    import unittest

    unittest.main()
