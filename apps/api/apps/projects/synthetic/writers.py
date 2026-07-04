from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .generator import GenerationResult, LogEvent, RequestEvent, SpanEvent

REQUEST_COLUMNS = [
    "timestamp",
    "app_id",
    "project_id",
    "endpoint_id",
    "environment",
    "method",
    "path",
    "status_code",
    "response_time_ms",
    "request_size",
    "response_size",
    "ip_address",
    "user_agent",
    "consumer_id",
    "consumer_name",
    "consumer_group",
    "request_payload",
    "response_payload",
    "request_headers",
    "response_headers",
    "base_url",
    "trace_id",
    "span_id",
]

LOG_COLUMNS = [
    "timestamp",
    "app_id",
    "project_id",
    "environment",
    "level",
    "message",
    "logger_name",
    "endpoint_method",
    "endpoint_path",
    "status_code",
    "consumer_id",
    "consumer_name",
    "consumer_group",
    "trace_id",
    "span_id",
    "payload",
    "attributes_json",
]

SPAN_COLUMNS = [
    "timestamp",
    "app_id",
    "project_id",
    "environment",
    "trace_id",
    "span_id",
    "parent_span_id",
    "name",
    "kind",
    "service_name",
    "duration_ms",
    "status",
    "status_code",
    "attributes_json",
]


@dataclass(frozen=True)
class WriteSummary:
    mode: str
    requests: int = 0
    logs: int = 0
    spans: int = 0
    output_dir: str = ""
    details: dict[str, Any] | None = None


class JsonlWriter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def write(self, result: GenerationResult) -> WriteSummary:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        request_path = self.output_dir / "requests.jsonl"
        log_path = self.output_dir / "logs.jsonl"
        span_path = self.output_dir / "spans.jsonl"
        manifest_path = self.output_dir / "manifest.json"

        request_count = _write_jsonl(request_path, (event.as_ingest_dict() for event in result.requests))
        log_count = _write_jsonl(log_path, (event.as_ingest_dict() for event in result.logs))
        span_count = _write_jsonl(span_path, (event.as_ingest_dict() for event in result.spans))
        manifest_path.write_text(json.dumps(result.summary(), indent=2, sort_keys=True), encoding="utf-8")

        return WriteSummary(
            mode="jsonl",
            requests=request_count,
            logs=log_count,
            spans=span_count,
            output_dir=str(self.output_dir),
            details={
                "requests": str(request_path),
                "logs": str(log_path),
                "spans": str(span_path),
                "manifest": str(manifest_path),
            },
        )


class HttpIngestWriter:
    def __init__(self, ingest_url: str, api_key: str, *, batch_size: int = 1000, timeout: float = 30.0) -> None:
        if not ingest_url:
            raise ValueError("ingest_url is required for HTTP ingest")
        if not api_key:
            raise ValueError("api_key is required for HTTP ingest")
        self.ingest_url = ingest_url.rstrip("/")
        self.api_key = api_key
        self.batch_size = max(1, min(int(batch_size), 1000))
        self.timeout = timeout

    def write(self, result: GenerationResult) -> WriteSummary:
        import httpx

        headers = {"X-API-Key": self.api_key}
        accepted_requests = accepted_logs = accepted_spans = 0
        with httpx.Client(timeout=self.timeout, headers=headers) as client:
            for batch in _chunks([event.as_ingest_dict() for event in result.requests], self.batch_size):
                response = client.post(f"{self.ingest_url}/v1/requests", json={"requests": batch})
                response.raise_for_status()
                accepted_requests += int(response.json().get("accepted", 0))
            for batch in _chunks([event.as_ingest_dict() for event in result.logs], self.batch_size):
                response = client.post(f"{self.ingest_url}/v1/logs", json={"logs": batch})
                response.raise_for_status()
                accepted_logs += int(response.json().get("accepted", 0))
            for batch in _chunks([event.as_ingest_dict() for event in result.spans], self.batch_size):
                response = client.post(f"{self.ingest_url}/v1/traces", json={"spans": batch})
                response.raise_for_status()
                accepted_spans += int(response.json().get("accepted", 0))

        return WriteSummary(mode="http", requests=accepted_requests, logs=accepted_logs, spans=accepted_spans)


class DirectClickHouseWriter:
    def __init__(self, *, batch_size: int = 1000) -> None:
        self.batch_size = max(1, min(int(batch_size), 1000))

    def write(self, result: GenerationResult) -> WriteSummary:
        from apps.projects.models import App, Endpoint
        from apps.projects.services import IngestService
        from core.database.clickhouse.client import get_clickhouse_client

        client = get_clickhouse_client()
        self._ensure_schema(client, IngestService)

        app_by_identifier = self._resolve_apps(App, result.requests)
        missing = sorted(
            {
                event.app_id or event.app_slug
                for event in result.requests
                if not self._app_for_event(event, app_by_identifier)
            }
        )
        if missing:
            raise ValueError(f"Cannot direct-write telemetry because app(s) were not found: {', '.join(missing)}")

        endpoint_map = self._ensure_endpoints(Endpoint, app_by_identifier, result.requests)
        accepted_requests = accepted_logs = accepted_spans = 0

        for batch in _chunks(result.requests, self.batch_size):
            rows = [self._request_row(event, app_by_identifier, endpoint_map) for event in batch]
            client.insert("api_requests", rows, columns=REQUEST_COLUMNS)
            accepted_requests += len(rows)

        for batch in _chunks(result.logs, self.batch_size):
            rows = [self._log_row(event, app_by_identifier) for event in batch]
            if rows:
                client.insert("api_logs", rows, columns=LOG_COLUMNS)
                accepted_logs += len(rows)

        for batch in _chunks(result.spans, self.batch_size):
            rows = [self._span_row(event, app_by_identifier) for event in batch]
            if rows:
                client.insert("api_spans", rows, columns=SPAN_COLUMNS)
                accepted_spans += len(rows)

        return WriteSummary(mode="direct", requests=accepted_requests, logs=accepted_logs, spans=accepted_spans)

    def _ensure_schema(self, client, ingest_service) -> None:
        for helper in (
            "ensure_payload_columns",
            "ensure_header_columns",
            "ensure_consumer_columns",
            "ensure_base_url_column",
            "ensure_api_logs_table",
            "ensure_api_spans_table",
        ):
            fn = getattr(ingest_service, helper, None)
            if fn:
                fn(client)

        for statement in (
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS project_id String CODEC(ZSTD(1))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS request_payload String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS response_payload String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS request_headers String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS response_headers String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS consumer_id String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS consumer_name String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS consumer_group String CODEC(ZSTD(3))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS base_url String DEFAULT '' CODEC(ZSTD(1))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS trace_id String DEFAULT '' CODEC(ZSTD(1))",
            "ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS span_id String DEFAULT '' CODEC(ZSTD(1))",
            "ALTER TABLE api_requests ADD INDEX IF NOT EXISTS idx_api_requests_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS project_id String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS endpoint_method LowCardinality(String) CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS endpoint_path String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS status_code UInt16 CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS consumer_id String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS consumer_name String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS consumer_group String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS trace_id String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS span_id String CODEC(ZSTD(1))",
            "ALTER TABLE api_logs ADD COLUMN IF NOT EXISTS attributes_json String CODEC(ZSTD(3))",
            "ALTER TABLE api_logs ADD INDEX IF NOT EXISTS idx_api_logs_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1",
        ):
            client.execute(statement)

        client.execute(
            """
            CREATE TABLE IF NOT EXISTS api_spans (
                timestamp DateTime64(3) CODEC(DoubleDelta, ZSTD(1)),
                app_id String CODEC(ZSTD(1)),
                project_id String CODEC(ZSTD(1)),
                environment LowCardinality(String) CODEC(ZSTD(1)),
                trace_id String CODEC(ZSTD(1)),
                span_id String CODEC(ZSTD(1)),
                parent_span_id String CODEC(ZSTD(1)),
                name String CODEC(ZSTD(1)),
                kind LowCardinality(String) CODEC(ZSTD(1)),
                service_name LowCardinality(String) CODEC(ZSTD(1)),
                duration_ms Float64 CODEC(Gorilla, ZSTD(1)),
                status LowCardinality(String) CODEC(ZSTD(1)),
                status_code UInt16 CODEC(ZSTD(1)),
                attributes_json String CODEC(ZSTD(3))
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (app_id, trace_id, timestamp)
            TTL toDateTime(timestamp) + INTERVAL 30 DAY
            SETTINGS index_granularity = 8192
            """
        )
        client.execute("ALTER TABLE api_spans ADD INDEX IF NOT EXISTS idx_api_spans_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1")
        client.execute("ALTER TABLE api_spans ADD INDEX IF NOT EXISTS idx_api_spans_project_id project_id TYPE bloom_filter(0.01) GRANULARITY 1")

    def _resolve_apps(self, app_model, requests: list[RequestEvent]) -> dict[str, Any]:
        app_ids = {event.app_id for event in requests if event.app_id}
        apps = list(app_model.objects.filter(id__in=app_ids, is_active=True).select_related("project")) if app_ids else []
        if not apps:
            slugs = {event.app_slug for event in requests if event.app_slug}
            apps = list(app_model.objects.filter(slug__in=slugs, is_active=True).select_related("project"))
        mapping: dict[str, Any] = {}
        for app in apps:
            mapping[str(app.id)] = app
            mapping.setdefault(app.slug, app)
        return mapping

    def _app_for_event(self, event: RequestEvent | LogEvent | SpanEvent, app_by_identifier: dict[str, Any]):
        return app_by_identifier.get(event.app_id) or app_by_identifier.get(event.app_slug)

    def _endpoint_key(self, event: RequestEvent, app_by_identifier: dict[str, Any]) -> tuple[str, str, str]:
        app = self._app_for_event(event, app_by_identifier)
        return (str(app.id), event.method.upper(), event.path)

    def _ensure_endpoints(self, endpoint_model, app_by_identifier: dict[str, Any], requests: list[RequestEvent]) -> dict[tuple[str, str, str], str]:
        seen: dict[tuple[str, str, str], datetime] = {}
        for event in requests:
            key = self._endpoint_key(event, app_by_identifier)
            previous = seen.get(key)
            if previous is None or event.timestamp > previous:
                seen[key] = event.timestamp

        endpoint_ids: dict[tuple[str, str, str], str] = {}
        for (app_id, method, path), last_seen_at in seen.items():
            endpoint, _created = endpoint_model.objects.update_or_create(
                app_id=app_id,
                method=method,
                path=path,
                defaults={
                    "description": "",
                    "is_active": True,
                    "last_seen_at": last_seen_at,
                },
            )
            endpoint_ids[(app_id, method, path)] = str(endpoint.id)
        return endpoint_ids

    def _request_row(self, event: RequestEvent, app_by_identifier: dict[str, Any], endpoint_map: dict[tuple[str, str, str], str]) -> dict[str, Any]:
        app = self._app_for_event(event, app_by_identifier)
        method = event.method.upper()
        endpoint_key = self._endpoint_key(event, app_by_identifier)
        return {
            "timestamp": event.timestamp,
            "app_id": str(app.id),
            "project_id": str(app.project_id),
            "endpoint_id": endpoint_map.get(endpoint_key, ""),
            "environment": event.environment,
            "method": method,
            "path": event.path,
            "status_code": event.status_code,
            "response_time_ms": event.response_time_ms,
            "request_size": event.request_size,
            "response_size": event.response_size,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "consumer_id": event.consumer_id,
            "consumer_name": event.consumer_name,
            "consumer_group": event.consumer_group,
            "request_payload": event.request_payload,
            "response_payload": event.response_payload,
            "request_headers": event.request_headers,
            "response_headers": event.response_headers,
            "base_url": event.base_url,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
        }

    def _log_row(self, event: LogEvent, app_by_identifier: dict[str, Any]) -> dict[str, Any]:
        app = self._app_for_event(event, app_by_identifier)
        return {
            "timestamp": event.timestamp,
            "app_id": str(app.id),
            "project_id": str(app.project_id),
            "environment": event.environment,
            "level": event.level,
            "message": event.message,
            "logger_name": event.logger_name,
            "endpoint_method": event.endpoint_method,
            "endpoint_path": event.endpoint_path,
            "status_code": event.status_code,
            "consumer_id": event.consumer_id,
            "consumer_name": event.consumer_name,
            "consumer_group": event.consumer_group,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "payload": event.payload,
            "attributes_json": json.dumps(event.attributes, separators=(",", ":"), sort_keys=True),
        }

    def _span_row(self, event: SpanEvent, app_by_identifier: dict[str, Any]) -> dict[str, Any]:
        app = self._app_for_event(event, app_by_identifier)
        return {
            "timestamp": event.timestamp,
            "app_id": str(app.id),
            "project_id": str(app.project_id),
            "environment": event.environment,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "parent_span_id": event.parent_span_id,
            "name": event.name,
            "kind": event.kind,
            "service_name": event.service_name,
            "duration_ms": event.duration_ms,
            "status": event.status,
            "status_code": event.status_code,
            "attributes_json": json.dumps(event.attributes, separators=(",", ":"), sort_keys=True),
        }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def _chunks(items, size: int):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]
