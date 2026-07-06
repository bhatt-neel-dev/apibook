"""Baseline-deviation anomaly detection for project endpoints.

Flags an endpoint when its error rate or p95 latency deviates from its own
trailing hour-of-day-matched baseline — no static, user-configured thresholds.

Model (design record in ANOMALY-ALERTS-PLAN.md):
  - Baseline: per (endpoint, metric), the median + MAD of 5-minute bucket values
    from the trailing 7 days, restricted to buckets in the same (and previous)
    hour of day as now — so 9am traffic is judged against 9am history, not
    3am quiet.
  - Anomaly: the last 3 consecutive 5-minute windows ALL exceed
    median + 3 * MAD. Requiring three windows makes single-bucket blips
    non-alertable by construction.
  - Floors: endpoints below MIN_REQUESTS_PER_WINDOW in any current window are
    skipped (a 1-request 100%-error window is noise, not signal), and fewer
    than MIN_BASELINE_SAMPLES history buckets means "no baseline yet", never
    "alert against a guess". MAD gets an absolute floor per metric so a
    perfectly flat baseline can't produce a hair-trigger threshold.

Deduplication: one AlertEvent per (project, endpoint, metric, UTC day), enforced
by AlertEvent.dedup_key's unique constraint — a sustained incident produces one
alert, not one per detection cycle.

Kill-switch: APILENS_ANOMALY_ALERTS follows the APILENS_CAPTURE_SPANS pattern —
unset means enabled, an explicitly falsey env value disables the job globally,
and the env var can only ever turn the feature OFF.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as tz

logger = logging.getLogger(__name__)

WINDOW_MINUTES = 5
CONSECUTIVE_WINDOWS = 3
BASELINE_DAYS = 7
MAD_MULTIPLIER = 3.0
MIN_REQUESTS_PER_WINDOW = 10
MIN_BASELINE_SAMPLES = 12
# Absolute MAD floors keep a flat baseline from alerting on trivial deviation:
# error rate is in percentage points; latency in milliseconds.
MAD_FLOOR = {"error_rate": 2.0, "latency": 15.0}

_FALSEY = {"0", "false", "no", "off", "disabled", ""}


def anomaly_alerts_enabled() -> bool:
    """Global kill-switch via APILENS_ANOMALY_ALERTS (env wins, off-only)."""
    raw = os.getenv("APILENS_ANOMALY_ALERTS")
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSEY


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median of empty list")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values: list[float], med: float) -> float:
    """Median absolute deviation — a robust spread measure (outlier-resistant)."""
    return median([abs(v - med) for v in values])


@dataclass(slots=True)
class Verdict:
    observed: float  # worst (max) of the offending windows
    baseline: float  # baseline median
    threshold: float  # median + MAD_MULTIPLIER * effective MAD


def evaluate_metric(
    current_windows: list[float],
    baseline_samples: list[float],
    kind: str,
) -> Verdict | None:
    """Judge the last CONSECUTIVE_WINDOWS values against the baseline.

    Returns a Verdict only when EVERY current window exceeds the threshold;
    returns None when there is no anomaly OR not enough data to say (too few
    current windows or baseline samples) — insufficient data must never alert.
    """
    if len(current_windows) < CONSECUTIVE_WINDOWS:
        return None
    if len(baseline_samples) < MIN_BASELINE_SAMPLES:
        return None

    med = median(baseline_samples)
    spread = max(mad(baseline_samples, med), MAD_FLOOR.get(kind, 0.0))
    threshold = med + MAD_MULTIPLIER * spread

    recent = current_windows[-CONSECUTIVE_WINDOWS:]
    if all(v > threshold for v in recent):
        return Verdict(observed=max(recent), baseline=med, threshold=threshold)
    return None


# ── ClickHouse window queries ──────────────────────────────────────────


def _bucketed_endpoint_metrics(
    client, project_id: str, since: datetime, until: datetime, hours: list[int] | None
) -> list[dict]:
    """Per-endpoint 5-minute bucket metrics for a project in [since, until].

    Buckets below MIN_REQUESTS_PER_WINDOW are excluded at the source: they are
    too sparse to be signal for the current windows and would drag baseline
    medians toward quiet-period values.
    """
    params = {
        "project_id": project_id,
        "since": since,
        "until": until,
        "min_requests": MIN_REQUESTS_PER_WINDOW,
    }
    hour_filter = ""
    if hours is not None:
        hour_filter = "AND toHour(timestamp) IN %(hours)s"
        params["hours"] = hours
    query = f"""
        SELECT
            app_id,
            method,
            path,
            toStartOfInterval(timestamp, INTERVAL {WINDOW_MINUTES} minute) AS bucket,
            count() AS total_requests,
            countIf(status_code >= 400) / count() * 100 AS error_rate,
            quantile(0.95)(response_time_ms) AS p95_response_time_ms
        FROM api_requests
        WHERE project_id = %(project_id)s
          AND timestamp >= %(since)s
          AND timestamp < %(until)s
          {hour_filter}
        GROUP BY app_id, method, path, bucket
        HAVING total_requests >= %(min_requests)s
        ORDER BY bucket ASC
    """
    return client.execute(query, params)


def _group_by_endpoint(rows: list[dict]) -> dict[tuple[str, str, str], list[dict]]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = (str(row["app_id"]), row["method"], row["path"])
        grouped.setdefault(key, []).append(row)
    return grouped


def detect_project_anomalies(project, now: datetime | None = None) -> int:
    """Run one detection cycle for a project; returns alerts created."""
    from core.database.clickhouse.client import get_clickhouse_client

    from .models import AlertEvent, App

    now = now or datetime.now(tz.utc)
    client = get_clickhouse_client()

    current_since = now - timedelta(minutes=WINDOW_MINUTES * CONSECUTIVE_WINDOWS)
    current_rows = _bucketed_endpoint_metrics(
        client, str(project.id), current_since, now, hours=None
    )
    if not current_rows:
        return 0

    # Baseline: trailing 7 days (excluding the current windows), same hour of
    # day as now plus the previous hour, so windows near an hour boundary still
    # have a like-for-like history to be judged against.
    hours = sorted({now.hour, (now.hour - 1) % 24})
    baseline_rows = _bucketed_endpoint_metrics(
        client,
        str(project.id),
        now - timedelta(days=BASELINE_DAYS),
        current_since,
        hours=hours,
    )

    current = _group_by_endpoint(current_rows)
    baseline = _group_by_endpoint(baseline_rows)
    apps_by_id = {str(a.id): a for a in App.objects.filter(project=project)}

    created = 0
    for key, windows in current.items():
        history = baseline.get(key)
        if not history:
            continue
        app_id, method, path = key
        for kind, field in (("error_rate", "error_rate"), ("latency", "p95_response_time_ms")):
            verdict = evaluate_metric(
                [float(w[field]) for w in windows],
                [float(h[field]) for h in history],
                kind,
            )
            if verdict is None:
                continue
            dedup_key = f"{kind}:{method}:{path}"[:549] + f":{now.date().isoformat()}"
            _, was_created = AlertEvent.objects.get_or_create(
                project=project,
                dedup_key=dedup_key,
                defaults={
                    "app": apps_by_id.get(app_id),
                    "kind": kind,
                    "method": method,
                    "path": path,
                    "observed_value": verdict.observed,
                    "baseline_value": verdict.baseline,
                    "threshold_value": verdict.threshold,
                    "window_start": current_since,
                    "window_end": now,
                },
            )
            if was_created:
                created += 1
                logger.info(
                    "anomaly alert: project=%s %s %s %s observed=%.1f baseline=%.1f threshold=%.1f",
                    project.slug, kind, method, path,
                    verdict.observed, verdict.baseline, verdict.threshold,
                )
    return created


HEARTBEAT_NAME = "detect_anomalies"
# A cycle every WINDOW_MINUTES; three missed cycles = stale (matches the
# 3-consecutive-window philosophy: one hiccup isn't an incident).
HEARTBEAT_STALE_AFTER_SECONDS = WINDOW_MINUTES * 60 * 3


def _record_heartbeat(scanned: int, created: int, duration_ms: int) -> None:
    from .models import JobHeartbeat

    try:
        JobHeartbeat.objects.update_or_create(
            name=HEARTBEAT_NAME,
            defaults={
                "last_run_at": datetime.now(tz.utc),
                "last_scanned": scanned,
                "last_created": created,
                "last_duration_ms": duration_ms,
            },
        )
    except Exception:
        # Monitoring must never take the job down with it.
        logger.exception("failed to record job heartbeat")


def run_detection_cycle(project_slugs: list[str] | None = None) -> tuple[int, int]:
    """Scan active projects; returns (projects_scanned, alerts_created).

    `project_slugs` restricts the cycle to named projects — the staged-rollout
    lever: run the job against dogfood/pilot projects only before opening it to
    everyone. Unknown slugs simply match nothing (scanned count exposes this).
    """
    import time

    from .models import Project

    if not anomaly_alerts_enabled():
        logger.info("anomaly detection disabled via APILENS_ANOMALY_ALERTS; skipping cycle")
        return 0, 0

    started = time.monotonic()
    scanned = 0
    created = 0
    projects = Project.objects.filter(is_active=True, anomaly_alerts_enabled=True)
    if project_slugs:
        projects = projects.filter(slug__in=project_slugs)
    for project in projects.iterator():
        scanned += 1
        try:
            created += detect_project_anomalies(project)
        except Exception:
            # One project's failure must not starve the rest of the cycle.
            logger.exception("anomaly detection failed for project %s", project.slug)
    _record_heartbeat(scanned, created, int((time.monotonic() - started) * 1000))
    return scanned, created


def job_health() -> dict:
    """Freshness snapshot for /health/jobs (no project data — safe unauthenticated)."""
    from .models import JobHeartbeat

    enabled = anomaly_alerts_enabled()
    hb = JobHeartbeat.objects.filter(name=HEARTBEAT_NAME).first()
    if hb is None:
        return {
            "name": HEARTBEAT_NAME,
            "enabled": enabled,
            "last_run_at": None,
            "age_seconds": None,
            # Never-ran only counts as stale when the job is supposed to run.
            "stale": enabled,
        }
    age = (datetime.now(tz.utc) - hb.last_run_at).total_seconds()
    return {
        "name": HEARTBEAT_NAME,
        "enabled": enabled,
        "last_run_at": hb.last_run_at.isoformat(),
        "age_seconds": int(age),
        "stale": enabled and age > HEARTBEAT_STALE_AFTER_SECONDS,
    }
