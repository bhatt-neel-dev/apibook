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

### Slice 5 — Scheduler wiring (next; blocks real usage)
The job exists but nothing runs it on cadence.
- Add an `alerts` proc to `mprocs.yaml` (dev): `manage.py detect_anomalies --loop` from `apps/api`.
- Add a service (or supervisor entry) to the production docker-compose running the same loop in the api image. New infra dependency — flagged at design time; failure modes to cover: silent death (mitigated by heartbeat monitoring below), double-run (safe: dedup makes cycles idempotent), resource contention (baseline cost measured at ~0.65s/cycle; re-measure at real scale before 100%).
- **Exit criteria:** heartbeat line visible in prod logs every 5 min for 48h; ClickHouse CPU delta < 10% vs pre-deploy baseline.

### Slice 6 — Heartbeat monitoring (G3 condition, partially met)
The heartbeat line exists; nothing yet alarms on its absence.
- Minimum viable: a Caddy/cron-side check (or Uptime-style monitor) that greps the last heartbeat age; > 15 min ⇒ notify.
- Dogfood option (preferred, per operating model §16.4): emit the heartbeat as a request into APILens's own pipeline so its absence is visible in the product itself.
- **Exit criteria:** deliberately stop the job in staging → notification arrives.

### Slice 7 — False-positive metric (the launch guardrail)
PRD guardrail: dismissal-without-click rate < 40%.
- Already have the data: `AlertEvent.dismissed_*` vs. View clicks (add a `viewed_at` timestamp set by a lightweight `POST .../alerts/{id}/seen` when View is clicked — one field + one endpoint + one line in the bell).
- A tiny management command or SQL to report weekly FP rate.
- **Exit criteria:** the number is computable from prod data; reviewed at day 7/14/30 (the refine/rollback/scrap decision input).

### Slice 8 — Alerts page + per-project settings toggle
- Full alert history page under `/projects/{slug}/alerts` (the bell caps at 20; history needs pagination — API already supports `status=all&limit`).
- Per-project opt-out: `Project.anomaly_alerts_enabled` boolean + settings toggle (deliberately deferred from v1 to avoid a dead `AlertRule` table; the global kill-switch covers ops needs meanwhile).
- **Exit criteria:** a user can disable alerts for one project without ops involvement.

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

- **Migrations are repo-gitignored** (`**/migrations/`): every environment must run `makemigrations projects && migrate` — the AlertEvent table does not arrive via git. Worth revisiting as a repo-wide convention (tracked migrations are the Django norm), but out of this feature's scope.
- **CI cannot run the DB-backed tests** until it generates migrations first (same root cause).
- Baseline queries scan per-project; at 100+ projects consider one batched query across projects per cycle (cheap refactor, not needed at current scale).
- The bell fetches on focus only; alerts appear on next focus/navigation, not via push — acceptable for v1, revisit with the alerts page.
