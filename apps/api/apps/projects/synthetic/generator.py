from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .accelerators import AcceleratorMode, RandomPlanner, RandomStreams
from .catalog import (
    AppProfile,
    ConsumerSegment,
    EndpointTemplate,
    IncidentProfile,
    ScenarioProfile,
    WeightedValue,
    expand_scenario_keys,
    get_scenario,
)


@dataclass(frozen=True)
class AppTarget:
    slug: str
    name: str = ""
    app_id: str = ""
    project_id: str = ""
    project_slug: str = ""
    framework: str = ""
    base_urls: tuple[str, ...] = ()

    @property
    def ingest_identifier(self) -> str:
        return self.app_id or self.slug


@dataclass(frozen=True)
class SyntheticRunConfig:
    scenario_keys: tuple[str, ...] = ("all",)
    count: int = 5000
    days: int = 14
    now: datetime | None = None
    seed: int | None = None
    accelerator: AcceleratorMode = "auto"
    include_logs: bool = True
    include_spans: bool = True
    project_slug: str = ""
    app_targets: tuple[AppTarget, ...] = ()


@dataclass(frozen=True)
class RequestEvent:
    timestamp: datetime
    app_id: str
    app_slug: str
    project_id: str
    project_slug: str
    scenario_key: str
    environment: str
    method: str
    path: str
    status_code: int
    response_time_ms: float
    request_size: int
    response_size: int
    ip_address: str
    user_agent: str
    consumer_id: str
    consumer_name: str
    consumer_group: str
    request_payload: str
    response_payload: str
    request_headers: str
    response_headers: str
    base_url: str
    trace_id: str
    span_id: str
    endpoint_service: str = ""
    endpoint_description: str = ""

    def as_ingest_dict(self) -> dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "app_id": self.app_id or self.app_slug,
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "request_size": self.request_size,
            "response_size": self.response_size,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "consumer_id": self.consumer_id,
            "consumer_name": self.consumer_name,
            "consumer_group": self.consumer_group,
            "request_payload": self.request_payload,
            "response_payload": self.response_payload,
            "request_headers": self.request_headers,
            "response_headers": self.response_headers,
            "base_url": self.base_url,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }


@dataclass(frozen=True)
class LogEvent:
    timestamp: datetime
    app_id: str
    app_slug: str
    project_id: str
    project_slug: str
    scenario_key: str
    environment: str
    level: str
    message: str
    logger_name: str
    endpoint_method: str
    endpoint_path: str
    status_code: int
    consumer_id: str
    consumer_name: str
    consumer_group: str
    trace_id: str
    span_id: str
    payload: str
    attributes: dict[str, str] = field(default_factory=dict)

    def as_ingest_dict(self) -> dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "app_id": self.app_id or self.app_slug,
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "level": self.level,
            "message": self.message,
            "logger_name": self.logger_name,
            "endpoint_method": self.endpoint_method,
            "endpoint_path": self.endpoint_path,
            "status_code": self.status_code,
            "consumer_id": self.consumer_id,
            "consumer_name": self.consumer_name,
            "consumer_group": self.consumer_group,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "payload": self.payload,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class SpanEvent:
    timestamp: datetime
    app_id: str
    app_slug: str
    project_id: str
    project_slug: str
    scenario_key: str
    environment: str
    trace_id: str
    span_id: str
    parent_span_id: str
    name: str
    kind: str
    service_name: str
    duration_ms: float
    status: str
    status_code: int
    attributes: dict[str, str] = field(default_factory=dict)

    def as_ingest_dict(self) -> dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "app_id": self.app_id or self.app_slug,
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "service_name": self.service_name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "status_code": self.status_code,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class GenerationResult:
    requests: list[RequestEvent]
    logs: list[LogEvent]
    spans: list[SpanEvent]
    scenarios: tuple[str, ...]
    accelerator_backend: str
    used_gpu: bool
    seed: int
    generated_at: datetime
    app_targets: tuple[AppTarget, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "requests": len(self.requests),
            "logs": len(self.logs),
            "spans": len(self.spans),
            "scenarios": list(self.scenarios),
            "accelerator_backend": self.accelerator_backend,
            "used_gpu": self.used_gpu,
            "seed": self.seed,
            "generated_at": self.generated_at.isoformat(),
            "apps": [target.slug for target in self.app_targets],
        }


class SyntheticTelemetryEngine:
    def __init__(self, config: SyntheticRunConfig) -> None:
        if config.count < 0:
            raise ValueError("count must be greater than or equal to 0")
        if config.days <= 0:
            raise ValueError("days must be greater than 0")
        self.config = config
        self.now = _normalize_now(config.now)
        self.scenario_keys = expand_scenario_keys(config.scenario_keys)
        self.scenarios = tuple(get_scenario(key) for key in self.scenario_keys)
        self.seed = config.seed if config.seed is not None else self._rotating_seed()
        self.rng = random.Random(self.seed)

    def generate(self) -> GenerationResult:
        planner = RandomPlanner(self.config.accelerator)
        streams = planner.plan(count=self.config.count, seed=self.seed)
        requests: list[RequestEvent] = []
        logs: list[LogEvent] = []
        spans: list[SpanEvent] = []
        app_targets_seen: dict[str, AppTarget] = {}

        for idx in range(self.config.count):
            scenario = _weighted_choice(self.scenarios, streams.scenario_roll[idx], "traffic_weight")
            endpoint = _weighted_choice(scenario.endpoints, streams.endpoint_roll[idx], "weight")
            app_profile = _app_profile_for_endpoint(scenario, endpoint, streams.app_roll[idx])
            app_target = self._resolve_app_target(app_profile, scenario)
            app_targets_seen[app_target.slug] = app_target
            consumer = _weighted_choice(scenario.consumers, streams.consumer_roll[idx], "weight")
            environment = _weighted_choice(scenario.environments, streams.environment_roll[idx], "weight").value
            timestamp = self._timestamp_for_roll(streams.time_roll[idx], consumer)
            path = _materialize_path(endpoint.path, self.rng)
            active_incident = _active_incident(scenario.incidents, endpoint, environment, streams.time_roll[idx])
            status_code = self._status_for(endpoint, consumer, active_incident, streams.status_roll[idx])
            latency_ms = self._latency_for(endpoint, consumer, active_incident, status_code, streams.latency_roll[idx], streams.tail_roll[idx])
            trace_id = _hex_id(self.rng, 32)
            span_id = _hex_id(self.rng, 16)
            consumer_id = _consumer_id(scenario.key, consumer, self.rng)
            base_url = self._base_url(app_target, app_profile)
            request_payload, response_payload = _payloads(
                endpoint=endpoint,
                scenario=scenario,
                path=path,
                status_code=status_code,
                consumer_id=consumer_id,
                rng=self.rng,
            )
            request_size = _request_size(endpoint, request_payload, streams.payload_roll[idx])
            response_size = _response_size(endpoint, response_payload, status_code, streams.tail_roll[idx])
            event = RequestEvent(
                timestamp=timestamp,
                app_id=app_target.app_id,
                app_slug=app_target.slug,
                project_id=app_target.project_id,
                project_slug=app_target.project_slug or self.config.project_slug,
                scenario_key=scenario.key,
                environment=environment,
                method=endpoint.method,
                path=path,
                status_code=status_code,
                response_time_ms=latency_ms,
                request_size=request_size,
                response_size=response_size,
                ip_address=_ip_address(self.rng),
                user_agent=self.rng.choice(consumer.user_agents),
                consumer_id=consumer_id,
                consumer_name=f"{consumer.name} {consumer_id.rsplit('-', 1)[-1]}",
                consumer_group=consumer.group,
                request_payload=request_payload,
                response_payload=response_payload,
                request_headers=_headers(trace_id, consumer, scenario, request=True),
                response_headers=_headers(trace_id, consumer, scenario, request=False),
                base_url=base_url,
                trace_id=trace_id,
                span_id=span_id,
                endpoint_service=endpoint.service_name,
                endpoint_description=endpoint.description,
            )
            requests.append(event)

            if self.config.include_logs:
                logs.extend(self._logs_for(event, endpoint, scenario, active_incident, streams.log_roll[idx]))

            if self.config.include_spans:
                spans.extend(self._spans_for(event, endpoint, scenario, active_incident, streams.span_roll[idx]))

        return GenerationResult(
            requests=requests,
            logs=logs,
            spans=spans,
            scenarios=self.scenario_keys,
            accelerator_backend=streams.backend,
            used_gpu=streams.used_gpu,
            seed=streams.seed,
            generated_at=self.now,
            app_targets=tuple(app_targets_seen.values()),
        )

    def _rotating_seed(self) -> int:
        hour_bucket = self.now.strftime("%Y%m%d%H")
        material = "|".join(
            [
                "apilens-synthetic",
                hour_bucket,
                ",".join(self.scenario_keys),
                str(self.config.count),
                str(self.config.days),
                self.config.project_slug,
                ",".join(target.slug for target in self.config.app_targets),
            ]
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return int(digest[:16], 16)

    def _resolve_app_target(self, app_profile: AppProfile, scenario: ScenarioProfile) -> AppTarget:
        if self.config.app_targets:
            by_slug = {target.slug: target for target in self.config.app_targets}
            if app_profile.slug in by_slug:
                return by_slug[app_profile.slug]
            # Allow a caller to provide fewer real apps than the scenario has
            # app profiles; weighted choice still spreads traffic over supplied
            # apps deterministically.
            index = int(self.rng.random() * len(self.config.app_targets))
            return self.config.app_targets[index]
        return AppTarget(
            slug=app_profile.slug,
            name=app_profile.name,
            project_slug=self.config.project_slug,
            framework=app_profile.framework,
            base_urls=app_profile.base_urls,
        )

    def _timestamp_for_roll(self, roll: float, consumer: ConsumerSegment) -> datetime:
        start = self.now - timedelta(days=self.config.days)
        day = int(min(0.999999, max(0.0, roll)) * self.config.days)
        if consumer.group in {"iot", "automation"}:
            seconds = self.rng.randint(0, 86_399)
        elif consumer.group in {"enterprise", "internal"}:
            seconds = int(self.rng.triangular(7 * 3600, 20 * 3600, 11 * 3600))
        else:
            seconds = int(self.rng.triangular(0, 86_399, 15 * 3600))
        return start + timedelta(days=day, seconds=max(0, min(seconds, 86_399)))

    def _status_for(
        self,
        endpoint: EndpointTemplate,
        consumer: ConsumerSegment,
        incident: IncidentProfile | None,
        roll: float,
    ) -> int:
        if incident and roll < incident.extra_error_rate:
            return incident.status_code
        if roll < consumer.base_error_rate:
            return 429 if consumer.group in {"free", "trial", "iot"} else 400
        adjusted_roll = min(0.999999, max(0.0, roll - consumer.base_error_rate))
        return _weighted_status(endpoint.status_weights, adjusted_roll)

    def _latency_for(
        self,
        endpoint: EndpointTemplate,
        consumer: ConsumerSegment,
        incident: IncidentProfile | None,
        status_code: int,
        latency_roll: float,
        tail_roll: float,
    ) -> float:
        profile = endpoint.latency
        value = profile.base_ms + (profile.jitter_ms * latency_roll)
        if tail_roll > 0.965:
            value += profile.tail_ms * ((tail_roll - 0.965) / 0.035)
        if status_code >= 500:
            value *= profile.error_multiplier
        elif status_code >= 400:
            value *= 1.18
        value *= consumer.latency_multiplier
        if incident:
            value *= incident.latency_multiplier
        return round(max(1.0, value), 2)

    def _base_url(self, app_target: AppTarget, app_profile: AppProfile) -> str:
        urls = app_target.base_urls or app_profile.base_urls
        return self.rng.choice(urls) if urls else ""

    def _logs_for(
        self,
        event: RequestEvent,
        endpoint: EndpointTemplate,
        scenario: ScenarioProfile,
        incident: IncidentProfile | None,
        roll: float,
    ) -> list[LogEvent]:
        should_log = event.status_code >= 500 or (event.status_code >= 400 and roll < 0.72) or roll < 0.10
        if not should_log:
            return []
        if event.status_code >= 500:
            level = "ERROR"
            message = f"{endpoint.service_name} returned {event.status_code} for {event.method} {endpoint.path}"
        elif event.status_code >= 400:
            level = "WARNING"
            message = f"{endpoint.service_name} rejected {event.method} {endpoint.path} with {event.status_code}"
        else:
            level = "INFO"
            message = f"{endpoint.service_name} completed {event.method} {endpoint.path}"
        attrs = {
            "scenario": scenario.key,
            "consumer_group": event.consumer_group,
            "endpoint_template": endpoint.path,
            "latency_ms": str(event.response_time_ms),
        }
        if incident:
            attrs["incident"] = incident.key
        return [
            LogEvent(
                timestamp=event.timestamp + timedelta(milliseconds=min(event.response_time_ms, 250)),
                app_id=event.app_id,
                app_slug=event.app_slug,
                project_id=event.project_id,
                project_slug=event.project_slug,
                scenario_key=event.scenario_key,
                environment=event.environment,
                level=level,
                message=message,
                logger_name=f"{endpoint.service_name}.request",
                endpoint_method=event.method,
                endpoint_path=event.path,
                status_code=event.status_code,
                consumer_id=event.consumer_id,
                consumer_name=event.consumer_name,
                consumer_group=event.consumer_group,
                trace_id=event.trace_id,
                span_id=event.span_id,
                payload=_json({"path": event.path, "status_code": event.status_code, "base_url": event.base_url}),
                attributes=attrs,
            )
        ]

    def _spans_for(
        self,
        event: RequestEvent,
        endpoint: EndpointTemplate,
        scenario: ScenarioProfile,
        incident: IncidentProfile | None,
        roll: float,
    ) -> list[SpanEvent]:
        status = "error" if event.status_code >= 500 else "ok"
        spans = [
            SpanEvent(
                timestamp=event.timestamp,
                app_id=event.app_id,
                app_slug=event.app_slug,
                project_id=event.project_id,
                project_slug=event.project_slug,
                scenario_key=event.scenario_key,
                environment=event.environment,
                trace_id=event.trace_id,
                span_id=event.span_id,
                parent_span_id="",
                name=f"{event.method} {endpoint.path}",
                kind="server",
                service_name=endpoint.service_name,
                duration_ms=event.response_time_ms,
                status=status,
                status_code=event.status_code,
                attributes={
                    "http.method": event.method,
                    "http.route": endpoint.path,
                    "consumer.group": event.consumer_group,
                    "scenario": scenario.key,
                },
            )
        ]
        child_count = 1 + int(roll * 3)
        remaining = max(event.response_time_ms * 0.74, 1.0)
        child_names = _child_span_names(endpoint, incident)
        parent_start_offset = 4.0
        for child_index in range(child_count):
            duration = max(1.0, remaining * self.rng.uniform(0.18, 0.42))
            remaining -= duration * 0.35
            name, kind = child_names[child_index % len(child_names)]
            spans.append(
                SpanEvent(
                    timestamp=event.timestamp + timedelta(milliseconds=parent_start_offset + child_index * 3),
                    app_id=event.app_id,
                    app_slug=event.app_slug,
                    project_id=event.project_id,
                    project_slug=event.project_slug,
                    scenario_key=event.scenario_key,
                    environment=event.environment,
                    trace_id=event.trace_id,
                    span_id=_hex_id(self.rng, 16),
                    parent_span_id=event.span_id,
                    name=name,
                    kind=kind,
                    service_name=endpoint.service_name,
                    duration_ms=round(duration, 2),
                    status=status if child_index == child_count - 1 and event.status_code >= 500 else "ok",
                    status_code=event.status_code if child_index == child_count - 1 else 0,
                    attributes={
                        "endpoint.template": endpoint.path,
                        "payload.kind": endpoint.payload_kind,
                        "scenario": scenario.key,
                    },
                )
            )
        return spans


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _weighted_choice(items: Iterable[Any], roll: float, weight_attr: str) -> Any:
    values = tuple(items)
    if not values:
        raise ValueError("weighted choice requires at least one item")
    total = sum(max(0.0, float(getattr(item, weight_attr))) for item in values)
    if total <= 0:
        return values[0]
    cursor = min(0.999999, max(0.0, roll)) * total
    running = 0.0
    for item in values:
        running += max(0.0, float(getattr(item, weight_attr)))
        if cursor <= running:
            return item
    return values[-1]


def _weighted_status(items: tuple[tuple[int, float], ...], roll: float) -> int:
    total = sum(max(0.0, weight) for _, weight in items)
    if total <= 0:
        return 200
    cursor = min(0.999999, max(0.0, roll)) * total
    running = 0.0
    for status, weight in items:
        running += max(0.0, weight)
        if cursor <= running:
            return int(status)
    return int(items[-1][0])


def _app_profile_for_endpoint(scenario: ScenarioProfile, endpoint: EndpointTemplate, roll: float) -> AppProfile:
    service_tokens = [token for token in endpoint.service_name.lower().replace("_", "-").split("-") if token]
    candidates: list[AppProfile] = []
    for profile in scenario.apps:
        searchable = " ".join([profile.slug, profile.name, profile.description]).lower()
        if any(token in searchable for token in service_tokens):
            candidates.append(profile)
    if candidates:
        return _weighted_choice(candidates, roll, "weight")
    return _weighted_choice(scenario.apps, roll, "weight")


def _active_incident(
    incidents: tuple[IncidentProfile, ...],
    endpoint: EndpointTemplate,
    environment: str,
    time_roll: float,
) -> IncidentProfile | None:
    for incident in incidents:
        if environment not in incident.environments:
            continue
        if not (incident.start_ratio <= time_roll <= incident.end_ratio):
            continue
        if any(fragment in endpoint.path for fragment in incident.path_contains):
            return incident
    return None


def _materialize_path(path: str, rng: random.Random) -> str:
    replacements = {
        "{api_id}": f"api_{rng.randint(1000, 9999)}",
        "{cart_id}": f"cart_{rng.randint(10000, 99999)}",
        "{consent_id}": f"consent_{rng.randint(1000, 9999)}",
        "{device_id}": f"dev_{rng.randint(100000, 999999)}",
        "{order_id}": f"ord_{rng.randint(100000, 999999)}",
        "{patient_token}": f"pt_{rng.randint(100000, 999999)}",
        "{payment_id}": f"pay_{rng.randint(100000, 999999)}",
        "{plan_id}": f"plan_{rng.choice(['free', 'pro', 'business', 'enterprise'])}",
        "{policy_id}": f"pol_{rng.randint(1000, 9999)}",
        "{product_id}": f"sku_{rng.randint(10000, 99999)}",
        "{route_id}": f"route_{rng.randint(1000, 9999)}",
        "{shipment_id}": f"ship_{rng.randint(100000, 999999)}",
        "{tenant_id}": f"tenant_{rng.randint(1000, 9999)}",
    }
    output = path
    for token, value in replacements.items():
        output = output.replace(token, value)
    return output


def _payloads(
    *,
    endpoint: EndpointTemplate,
    scenario: ScenarioProfile,
    path: str,
    status_code: int,
    consumer_id: str,
    rng: random.Random,
) -> tuple[str, str]:
    request: dict[str, Any] = {
        "scenario": scenario.key,
        "consumer_id": consumer_id,
        "request_id": f"req_{rng.randint(1000000, 9999999)}",
    }
    kind = endpoint.payload_kind
    if endpoint.method == "GET":
        request = {}
    elif kind in {"payment", "checkout", "payout"}:
        request.update({"amount": rng.randint(900, 250000) / 100, "currency": rng.choice(["USD", "EUR", "INR", "GBP"]), "idempotency_key": f"idem_{rng.randint(100000, 999999)}"})
    elif kind in {"completion", "embedding", "moderation"}:
        request.update({"model": rng.choice(["apex-mini", "apex-pro", "embed-small"]), "input_tokens": rng.randint(24, 4096), "prompt_ref": f"prompt_{rng.randint(1000, 9999)}"})
    elif kind in {"telemetry", "position"}:
        request.update({"device_ref": f"dev_{rng.randint(100000, 999999)}", "sample_count": rng.randint(1, 200), "battery_pct": rng.randint(4, 100)})
    elif kind in {"patient", "appointment", "claim", "eligibility"}:
        request.update({"patient_token": f"pt_{rng.randint(100000, 999999)}", "facility_code": f"fac_{rng.randint(100, 999)}", "test_data": True})
    elif kind in {"webhook", "notification"}:
        request.update({"destination_ref": f"dest_{rng.randint(1000, 9999)}", "event_type": rng.choice(["created", "updated", "failed", "delivered"])})
    else:
        request.update({"entity_ref": f"{kind}_{rng.randint(100000, 999999)}"})

    if status_code >= 400:
        response = {
            "ok": False,
            "error": {
                "code": _error_code(status_code),
                "message": "Synthetic error generated for APILens QA data.",
            },
            "path": path,
        }
    else:
        response = {
            "ok": True,
            "status": status_code,
            "result_ref": f"{kind}_{rng.randint(1000000, 9999999)}",
        }
        if kind in {"completion", "embedding", "token_meter"}:
            response["usage"] = {"input_tokens": rng.randint(20, 4096), "output_tokens": rng.randint(8, 2048)}
        if kind in {"usage", "quota"}:
            response["quota"] = {"used": rng.randint(1, 95), "limit": 100}

    return (_json(request) if request else "", _json(response))


def _error_code(status_code: int) -> str:
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "authentication_required"
    if status_code == 402:
        return "payment_required"
    if status_code == 403:
        return "permission_denied"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 413:
        return "payload_too_large"
    if status_code == 422:
        return "validation_error"
    if status_code == 429:
        return "rate_limited"
    if status_code in {502, 503, 504}:
        return "upstream_unavailable"
    return "internal_error"


def _request_size(endpoint: EndpointTemplate, payload: str, roll: float) -> int:
    baseline = 120 + len(payload.encode("utf-8"))
    multiplier = 1 + (roll * 2.5)
    if endpoint.payload_kind in {"completion", "embedding", "spec"}:
        multiplier *= 2.8
    return int(baseline * multiplier)


def _response_size(endpoint: EndpointTemplate, payload: str, status_code: int, roll: float) -> int:
    baseline = 220 + len(payload.encode("utf-8"))
    multiplier = 1 + (roll * 4.5)
    if endpoint.payload_kind in {"catalog", "api_catalog", "audit", "ledger"}:
        multiplier *= 3.2
    if status_code >= 400:
        multiplier *= 0.65
    return int(baseline * multiplier)


def _headers(trace_id: str, consumer: ConsumerSegment, scenario: ScenarioProfile, *, request: bool) -> str:
    if request:
        return _json(
            {
                "content-type": "application/json",
                "x-request-source": consumer.group,
                "x-scenario": scenario.key,
                "traceparent": f"00-{trace_id}-{trace_id[:16]}-01",
            }
        )
    return _json({"content-type": "application/json", "x-synthetic-data": "true"})


def _consumer_id(scenario_key: str, consumer: ConsumerSegment, rng: random.Random) -> str:
    return f"{scenario_key[:8]}-{consumer.group}-{rng.randint(1000, 9999)}"


def _ip_address(rng: random.Random) -> str:
    block = rng.choice(("192.0.2", "198.51.100", "203.0.113"))
    return f"{block}.{rng.randint(1, 254)}"


def _hex_id(rng: random.Random, length: int) -> str:
    bits = length * 4
    return f"{rng.getrandbits(bits):0{length}x}"[-length:]


def _child_span_names(endpoint: EndpointTemplate, incident: IncidentProfile | None) -> tuple[tuple[str, str], ...]:
    names = [
        (f"{endpoint.service_name}.validate", "internal"),
        (f"{endpoint.service_name}.db", "db"),
        (f"{endpoint.service_name}.cache", "internal"),
    ]
    if endpoint.payload_kind in {"payment", "risk", "eligibility", "webhook", "notification", "completion", "embedding"}:
        names.append((f"{endpoint.service_name}.upstream", "client"))
    if incident:
        names.append((f"{endpoint.service_name}.{incident.key}", "client"))
    return tuple(names)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
