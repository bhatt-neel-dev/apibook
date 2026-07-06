# Anomaly Alerts — Implementation Plan & Validation Record

Feature: baseline-deviation anomaly alerts (OPERATING-MODEL.md §17 worked example).
Branch: `dharmik-anomaly-alerts`. Status: **core shipped & live-verified; rollout slices below.**

---

## 1. What is DONE (validated, on this branch)

| Slice | Contents | Validation evidence |
|---|---|---|
| 1. Schema | `AlertEvent` model + migration (dedup unique constraint, dismissal audit fields) | Applied against real Postgres; note: repo gitignores ALL migrations — envs regenerate via `makemigrations` |
| 2. Detection | `apps/projects/anomaly.py` (hour-matched 7-day median+MAD, 3-consecutive-window rule, traffic/baseline/MAD floors), `detect_anomalies` command (one-shot + `--loop`, heartbeat line) | 19 unit+DB tests; live seeded scenario fired both alert kinds with correct values; re-run created 0 (dedup); per-cycle cost baseline: **~0.65s for 8 projects / ~7k rows** |
| 3. API | `GET /projects/alerts/recent`, `GET /projects/{slug}/alerts`, `POST .../alerts/{id}/dismiss` (write-authz, audit trail) | Live negative-authz matrix below; idempotent re-dismiss 200; bogus id 404; wrong-project-namespace 404 |
| 4. UI | Bell shows alerts + invitations; View → traffic page; Dismiss persists | Playwright: badge 2 → dismiss → 1; `dismissed_by` recorded; zero console errors |
| Kill-switch | `APILENS_ANOMALY_ALERTS` (env-wins, off-only, mirrors `APILENS_CAPTURE_SPANS`) | Live: server restarted with flag off → `status=all` returns `[]` despite 2 DB rows; flag on (positive control) → both rows return; job skips with log line |

### Negative-authz matrix (live-proven — mandatory because OPA is fail-open)

| Caller | List project alerts | Recent feed | Dismiss |
|---|---|---|---|
| Non-member | **403** ✔ | `[]` (no leakage) ✔ | — |
| Viewer member | 200 ✔ | sees project's alerts ✔ | **403** ✔ (write required) |
| Owner | 200 ✔ | ✔ | 200; idempotent; audit-trailed ✔ |

---

## 2. Remaining work, sequenced

Each slice is independently shippable; stop-safe after every row.

### Slice 5 — Scheduler wiring ✅ DONE
`alerts` proc in `mprocs.yaml` (dev) + `alerts-job` service in the prod compose (backend image, `restart: unless-stopped`, healthy-DB dependencies, kill-switch env passthrough). QA caught and fixed a real bug: heartbeat lines sat in Python's stdout buffer under a pipe — explicit flush added so heartbeat monitoring can't mistake a healthy job for a dead one. Verified: 3 live heartbeats in loop mode, kill-switch loop exits immediately, `docker compose config` resolves.

### Slice 6 — Heartbeat monitoring ✅ DONE
`JobHeartbeat` row written per cycle + unauthenticated `GET /health/jobs` reporting `{enabled, last_run_at, age_seconds, stale}` per job (stale = >3 missed cycles, only while enabled; kill-switched = "off", not "stale"). External monitors need one URL. Verified live both directions (fresh after cycle; stale after aging the row 20 min) + 4 tests including the exact threshold boundary. Remaining follow-up: point an actual external uptime monitor at `/health/jobs` in prod.

### Slice 7 — False-positive metric ✅ DONE
`AlertEvent.viewed_at` (first view wins, guarded update), `POST .../alerts/{id}/seen` (read access), bell + alerts-page links fire it fire-and-forget, `alert_fp_report` command prints the dismissal-without-view rate with an explicit GUARDRAIL BREACHED marker at ≥40%. Verified: idempotency proven live, report math exact against known state (50% for 1-viewed-of-2-dismissed).

### Slice 8 — Alerts page + per-project toggle ✅ DONE
`/projects/{slug}/alerts` (Active/Dismissed/All tabs, dismiss-in-place, deviation detail) + "Alerts" sidebar nav + `Project.anomaly_alerts_enabled` toggle on project settings (admin-only PATCH; the detector skips disabled projects entirely — zero query cost, not just suppressed alerts). QA caught and fixed a real bug: the BFF PATCH route silently dropped the new field (destructured only name/description) — UI showed success while Postgres kept the old value.

### Slice 9 — Tuning follow-ups (only if Slice-7 data demands)
Candidates, in order of expected value: raise `CONSECUTIVE_WINDOWS` for low-traffic endpoints; per-endpoint minimum-traffic floor scaling; weekly-digest delivery mode (the worked example's scrap-scenario learning — validate demand first).

### Explicitly out of scope (unchanged from PRD)
Email/Slack delivery; user-configurable static thresholds; per-consumer anomalies; ML models beyond median+MAD.

---

## 3. Rollout & rollback (G4/G5 recap for the production deploy)

- **Order:** migrate (additive-only) → deploy api image (endpoints live, harmless without job) → start job for dogfood project(s) only → watch 48h → all projects.
- **Staged gating:** the job is the natural gate — run it, initially, only against chosen projects if needed (a `--project` filter flag is a 5-line addition if staging by project is wanted).
- **G5 thresholds:** new-path (alerts API) error rate < 0.5%; ClickHouse CPU delta < 10%; VM RAM delta < 15%; FP/dismissal rate < 40% (day-7 check).
- **Rollback:** set `APILENS_ANOMALY_ALERTS=false` (stops job + empties APIs in one restart, proven live); orphaned `AlertEvent` rows are harmless by design; no destructive migration exists to unwind. Two rollbacks of this feature ⇒ escalate to redesign review per the operating model's three-strikes rule.

## 4. Known debts / cautions

- ~~Migrations are repo-gitignored~~ **FIXED**: the `**/migrations/` gitignore rule turned out to also exclude the ClickHouse `.sql` migrations — a CI-built image could create *neither* schema, despite the prod compose's `migrate` service depending on both. All Django + ClickHouse migrations are now tracked; verified by migrating a completely fresh Postgres from a `git archive` checkout (tracked files only) and a zero-drift `makemigrations --check`. CI can now also run the DB-backed tests.
- Staged rollout now has its lever: `detect_anomalies --project <slug>` (repeatable, composes with `--loop`).
- Baseline queries scan per-project; at 100+ projects consider one batched query across projects per cycle (cheap refactor, not needed at current scale).
- The bell fetches on focus only; alerts appear on next focus/navigation, not via push — acceptable for v1, revisit with the alerts page.
