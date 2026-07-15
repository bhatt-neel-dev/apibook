"""PII redaction and UTF-8-safe payload decoding.

Shared by the ASGI and WSGI middlewares so request/response capture behaves
identically across frameworks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, quote, urlencode

REDACTED = "[redacted]"

# Header names whose VALUES must never leave the app (case-insensitive).
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-amz-security-token",
        "x-csrf-token",
    }
)

# Cap on the serialized header JSON so a pathological request can't bloat a row.
_MAX_HEADER_BYTES = 8192

# How deep redact_body() walks nested JSON before giving up (guards against
# adversarially deep documents; typical API bodies are < 10 levels).
_MAX_BODY_DEPTH = 32


class Redactor:
    """Compiled PII redaction rules for captured request data.

    Built once per middleware from user-supplied regex lists; every pattern is
    matched case-insensitively with ``re.search`` against the *name* of the
    thing being redacted (query parameter, header, or JSON body field). Use
    anchors for exact matches (``r"^card_number$"``).

    Values are replaced with ``[redacted]``; names stay visible so the request
    log still shows *what* was sent, never the sensitive value itself.
    """

    __slots__ = ("query_params", "headers", "body_fields")

    def __init__(
        self,
        query_params: Sequence[str] = (),
        headers: Sequence[str] = (),
        body_fields: Sequence[str] = (),
    ) -> None:
        self.query_params = [re.compile(p, re.IGNORECASE) for p in (query_params or ())]
        self.headers = [re.compile(p, re.IGNORECASE) for p in (headers or ())]
        self.body_fields = [re.compile(p, re.IGNORECASE) for p in (body_fields or ())]

    @staticmethod
    def _matches(patterns: list[re.Pattern[str]], name: str) -> bool:
        return any(p.search(name) for p in patterns)

    def header_matches(self, name: str) -> bool:
        return bool(self.headers) and self._matches(self.headers, name)

    def redact_query(self, query: str) -> str:
        """Redact matching parameter values within a raw query string.

        Unparseable input is passed through untouched — capture must never
        break a request over a weird query string.
        """
        if not query or not self.query_params:
            return query
        try:
            pairs = parse_qsl(query, keep_blank_values=True)
            if not pairs:
                return query
            return urlencode(
                [(k, REDACTED if self._matches(self.query_params, k) else v) for k, v in pairs],
                # Keep "[redacted]" readable in the request log instead of %5Bredacted%5D.
                quote_via=lambda s, safe, enc, err: quote(s, safe=str(safe) + "[]", encoding=enc, errors=err),
            )
        except Exception:
            return query

    def redact_body(self, payload: str) -> str:
        """Redact matching field values in a JSON body (recursively).

        Non-JSON payloads are returned unchanged — field-level redaction only
        makes sense for structured bodies.
        """
        if not payload or not self.body_fields:
            return payload
        try:
            data = json.loads(payload)
        except Exception:
            return payload
        if not isinstance(data, (dict, list)):
            return payload

        def walk(node, depth: int):
            if depth > _MAX_BODY_DEPTH:
                return node
            if isinstance(node, dict):
                return {
                    k: REDACTED if self._matches(self.body_fields, str(k)) else walk(v, depth + 1)
                    for k, v in node.items()
                }
            if isinstance(node, list):
                return [walk(v, depth + 1) for v in node]
            return node

        try:
            return json.dumps(walk(data, 0), separators=(",", ":"), ensure_ascii=False)
        except Exception:
            return payload


def decode_utf8_safe(data: bytes) -> str:
    """Decode UTF-8, dropping an incomplete multibyte sequence at the tail.

    Payloads are captured by byte budget, so the cut can land in the middle of a
    multibyte character (common for non-ASCII / non-English text). Trimming the
    dangling continuation bytes before decoding avoids the trailing ``�`` that
    ``errors="replace"`` would otherwise produce.
    """
    if not data:
        return ""
    # Walk back over trailing UTF-8 continuation bytes (0b10xxxxxx). At most 3
    # can precede the lead byte of a 4-byte sequence.
    cut = len(data)
    for _ in range(4):
        try:
            return data[:cut].decode("utf-8")
        except UnicodeDecodeError as exc:
            # Re-raise if the error isn't at the very end (genuinely malformed).
            if exc.start < cut - 4:
                break
            cut = exc.start
    return data.decode("utf-8", errors="replace")


def serialize_headers(
    headers: dict[str, str],
    *,
    max_bytes: int = _MAX_HEADER_BYTES,
    redactor: Redactor | None = None,
) -> str:
    """Serialize a header map to a compact JSON string, redacting secrets.

    Returns ``""`` when there are no headers. Sensitive values are replaced with
    ``[redacted]`` — the built-in :data:`SENSITIVE_HEADERS` always apply, and a
    ``redactor`` adds the app's own header patterns on top. The whole blob is
    capped so it can't dominate a row.
    """
    if not headers:
        return ""
    safe: dict[str, str] = {}
    for key, value in headers.items():
        name = (key or "").lower()
        if not name:
            continue
        sensitive = name in SENSITIVE_HEADERS or (redactor is not None and redactor.header_matches(name))
        safe[name] = REDACTED if sensitive else str(value)
    if not safe:
        return ""
    blob = json.dumps(safe, separators=(",", ":"), ensure_ascii=False)
    if len(blob.encode("utf-8")) > max_bytes:
        # Drop keys (longest values first) until it fits.
        for name, _ in sorted(safe.items(), key=lambda kv: len(kv[1]), reverse=True):
            del safe[name]
            blob = json.dumps(safe, separators=(",", ":"), ensure_ascii=False)
            if len(blob.encode("utf-8")) <= max_bytes:
                break
    return blob
