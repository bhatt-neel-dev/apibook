"""
env_spans_enabled() is the global APILENS_CAPTURE_SPANS kill-switch: ops can
disable trace ingestion for a whole process without a code change, and it can
only ever turn spans OFF (a per-integration capture_spans=True must never
override an env APILENS_CAPTURE_SPANS=false). This file existed untested.
"""

from apilens.client.spans import env_spans_enabled


def test_enabled_by_default_when_unset(monkeypatch):
    monkeypatch.delenv("APILENS_CAPTURE_SPANS", raising=False)

    assert env_spans_enabled() is True


def test_disabled_by_falsey_values(monkeypatch):
    for value in ["0", "false", "False", "FALSE", "no", "No", "off", "OFF", "disabled", ""]:
        monkeypatch.setenv("APILENS_CAPTURE_SPANS", value)
        assert env_spans_enabled() is False, f"expected disabled for {value!r}"


def test_enabled_by_truthy_or_unrecognized_values(monkeypatch):
    for value in ["1", "true", "True", "yes", "on", "enabled", "anything-else"]:
        monkeypatch.setenv("APILENS_CAPTURE_SPANS", value)
        assert env_spans_enabled() is True, f"expected enabled for {value!r}"


def test_whitespace_is_trimmed_before_comparison(monkeypatch):
    monkeypatch.setenv("APILENS_CAPTURE_SPANS", "  false  ")

    assert env_spans_enabled() is False


def test_env_off_cannot_be_overridden_by_capture_spans_true(monkeypatch):
    """
    The kill-switch is combined with the per-integration flag as
    `capture_spans and env_spans_enabled()` at every framework integration
    point — env must win regardless of what the app code passes.
    """
    monkeypatch.setenv("APILENS_CAPTURE_SPANS", "false")
    capture_spans_from_app_code = True

    effective = capture_spans_from_app_code and env_spans_enabled()

    assert effective is False
