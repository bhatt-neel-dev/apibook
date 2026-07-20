"""
_sanitize.py is shared by every ASGI/WSGI middleware for request/response
capture: header redaction (never leak secrets to the ingest pipeline) and
UTF-8-safe decoding of byte-budget-truncated payloads. Untested until now.
"""

import json

from apilens.client._sanitize import decode_utf8_safe, serialize_headers, SENSITIVE_HEADERS, REDACTED


def test_sensitive_headers_are_redacted():
    headers = {"Authorization": "Bearer secret-token", "X-Api-Key": "sk_live_abc"}

    blob = serialize_headers(headers)
    parsed = json.loads(blob)

    assert parsed["authorization"] == REDACTED
    assert parsed["x-api-key"] == REDACTED


def test_redaction_is_case_insensitive_on_header_name():
    headers = {"COOKIE": "session=abc123", "Set-Cookie": "session=abc123"}

    parsed = json.loads(serialize_headers(headers))

    assert parsed["cookie"] == REDACTED
    assert parsed["set-cookie"] == REDACTED


def test_non_sensitive_headers_pass_through_unmodified():
    headers = {"Content-Type": "application/json", "X-Request-Id": "req-1"}

    parsed = json.loads(serialize_headers(headers))

    assert parsed["content-type"] == "application/json"
    assert parsed["x-request-id"] == "req-1"


def test_every_sensitive_header_name_is_redacted():
    headers = {name: "should-not-leak" for name in SENSITIVE_HEADERS}

    parsed = json.loads(serialize_headers(headers))

    assert all(value == REDACTED for value in parsed.values())


def test_empty_headers_returns_empty_string():
    assert serialize_headers({}) == ""
    assert serialize_headers(None) == ""


def test_header_blob_is_capped_at_max_bytes():
    headers = {f"x-custom-{i}": "v" * 500 for i in range(50)}

    blob = serialize_headers(headers, max_bytes=1024)

    assert len(blob.encode("utf-8")) <= 1024


def test_decode_utf8_safe_handles_clean_ascii():
    assert decode_utf8_safe(b"hello world") == "hello world"


def test_decode_utf8_safe_handles_empty_bytes():
    assert decode_utf8_safe(b"") == ""


def test_decode_utf8_safe_drops_truncated_multibyte_tail():
    # "café" encodes to b'caf\xc3\xa9' (é = 2 bytes); truncating mid-character
    # would normally produce a trailing U+FFFD replacement character.
    full = "café".encode("utf-8")
    truncated = full[:-1]

    result = decode_utf8_safe(truncated)

    assert result == "caf"
    assert "�" not in result


def test_decode_utf8_safe_falls_back_to_replace_for_genuinely_malformed_bytes():
    malformed = b"hello \xff\xfe world"

    result = decode_utf8_safe(malformed)

    assert "hello" in result
    assert "world" in result
