from datetime import timezone as tz
from unittest import TestCase

from apps.projects.services import _resolve_time_range
from core.exceptions.base import ValidationError


class TimeRangeTests(TestCase):
    def test_invalid_since_rejected_as_validation_error(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Invalid since timestamp"):
            _resolve_time_range("not-a-date", None)

    def test_invalid_until_rejected_as_validation_error(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Invalid until timestamp"):
            _resolve_time_range("2026-01-01T00:00:00Z", "also-bad")

    def test_reversed_range_rejected_as_validation_error(self) -> None:
        with self.assertRaisesRegex(ValidationError, "since.*before.*until"):
            _resolve_time_range("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")

    def test_valid_z_timestamps_are_utc(self) -> None:
        since, until = _resolve_time_range("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z")

        self.assertEqual(since.tzinfo, tz.utc)
        self.assertEqual(until.tzinfo, tz.utc)
        self.assertLess(since, until)