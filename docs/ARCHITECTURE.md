# Architecture

## System overview

```
 ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
 │  TMS (ENG)  │   │ SMMS (SNT)  │   │ TDMS (TRD)  │   │  COA (Ctrl) │
 │ track defs  │   │ signalling  │   │  OHE / elec │   │ TT + windows│
 └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
        └─────────────────┴──────┬──────────┴─────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │   Data Integration     │  normalize + merge
                    │  (services/data_...)   │  → MaintenanceTask
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  AI Prioritization     │  HistGradientBoosting + drivers
                    │  (ml/ + services/ai_)  │  → Critical/High/Med/Low
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  Traffic Forecast      │  pax (timetable) + goods (model)
                    └───────────┬────────────┘  → disruption per window
                                ▼
                    ┌────────────────────────┐
                    │  Block Planning +      │  corridor/location grouping
                    │  OR-Tools Optimization │  CP-SAT → MaintenanceBlock
                    └───────────┬────────────┘
                                ▼
            ┌───────────────────┴────────────────────┐
            ▼                                         ▼
    ┌───────────────┐                        ┌────────────────┐
    │ FastAPI REST  │  ◀── React + Tailwind ─│  Dashboard /   │
    │  /api/v1/...  │                        │  Charts / Map  │
    └───────┬───────┘                        └────────────────┘
            ▼
    ┌───────────────┐
    │ PDF / Excel   │
    │   reports     │
    └───────────────┘
```

## Data model

- **Corridor** 1─* **Station**
- **MaintenanceTask** — unified, department-agnostic record (keeps `source_system`
  for provenance) with AI outputs (`priority_label`, `priority_score`,
  `priority_explanation`).
- **Train** & **MaintenanceWindow** — COA timetable and granted windows.
- **MaintenanceBlock** 1─* **BlockTask** *─1 **MaintenanceTask** — optimizer output,
  with approval fields (`approved_by/at`, `approval_note`), `plan_version` and a
  JSON `explanation`.
- **MaintenanceWindow.status** — GRANTED / CANCELLED (Control) / REJECTED (block refused).
- **MaintenanceTask** also keeps `ai_priority_label`, `priority_factors` (JSON),
  `priority_source` (AI / CONTROLLER) and `override_reason`.
- **PlanVersion** — one row per (re)plan: trigger, reason, actor, solver status,
  solve time, objective, #variables, #constraints and a compact diff.
- **AuditEvent** — append-only record of approvals, rejections, overrides,
  live events and voided approvals.
- **Scenario** — a saved what-if (parameters + metrics only).

Everything lives in the one existing database (SQLite dev / PostgreSQL prod).
New columns are added in place by the start-up migration in `core/database.py`.

## AI prioritization

Features: `severity`, `asset_criticality`, `overdue_days`, `traffic_gmt`,
`estimated_duration_min`, `requires_traffic_block`, `gang_size`, engineered
`sla_pressure` (`log1p(overdue)·severity`) and `traffic_impact`
(`traffic·(1+block)`), plus one-hot department.

Target labels come from a domain-weighted **priority index** (0.32·severity +
0.24·criticality + 0.20·overdue + 0.16·traffic + 0.08·block), binned into four
ordered classes. A scikit-learn HistGradientBoosting classifier (class-balanced)
learns and generalizes this policy.

- **Score** = probability-weighted ordinal value (0.15 Low … 0.95 Critical), so
  tasks inside one class are still ranked.
- **Local drivers** — for each factor group (severity, criticality, overdue,
  traffic, block, duration, gang, department) the group is replaced by values
  from a fixed 24-row background sample; the average drop in score is that
  factor's signed impact for this task. No SHAP/LIME dependency.
- **Safety rule** — severity 5 on an asset with criticality ≥ 4 is never below
  High; the explanation says when the rule fired.
- **Human override** — needs a reason; the AI label is kept alongside, re-scoring
  never replaces a controller decision, and "Revert to AI" restores it.
- Global importances shown in Reports are permutation importances.

## Traffic forecasting

`services/traffic_forecast.py`. Goods trains are not timetabled, so a Poisson
HistGradientBoosting regressor learns hourly counts from 7 days of actual
running (features: corridor GMT, hour + sin/cos, Sunday flag, pax/goods flag).
For plan dates, passenger counts come from the timetable, goods from the model.
Back-test on the last 2 history days is stored in `model_meta.json`
(`mae_trains_per_hour` vs. a same-hour average baseline). The model retrains
automatically (~1 s) when the running data changes.

Window disruption = min(1, (pax + 0.7·goods) / 12) — replacing the old static
night/day rule (still the fallback if forecasting is unavailable).

## Optimization (OR-Tools CP-SAT)

**Decision variables**
- `present[t,w] ∈ {0,1}` — task `t` placed in window `w` (same corridor only).
- Optional interval `iv[t,w]` of duration `dur(t)` inside `[0, len(w)]`.
- `used[w]` — a block is opened for window `w`.

**Constraints**
- Each task placed in **at most one** window: `Σ_w present[t,w] ≤ 1`.
- A (task, window) pair exists only if the whole job fits in the window — work
  is never truncated.
- **Cumulative** capacity per window = `PARALLEL_GANGS` (parallel works, makespan
  fits inside the granted window).
- Windows per corridor are non-overlapping by construction ⇒ **no overlapping
  maintenance on the same corridor**.
- `used[w] = OR_t present[t,w]`; makespan `= max` end of placed intervals.

**Objective (maximize)**
```
Σ present[t,w]·(W_PRIORITY·score_t)          # coverage weighted by AI priority
 − Σ used[w]·(W_BLOCK + W_DISRUPTION·disruption_w)   # fewer, low-disruption blocks
 + Σ (extra departments in w)·W_MULTIDEPT    # reward multi-department coordination
```

`disruption_w` comes from the traffic forecast (trains held during the window).
Presets used by what-if: `balanced`, `max_coverage`, `min_disruption`. The result: fewer line possessions, high-priority work
done first, and Engineering/S&T/Traction work combined into shared blocks
wherever feasible.

## Dynamic rescheduling

`services/rescheduling.py` — events: `EMERGENCY_DEFECT`, `WINDOW_CANCELLED`,
`WINDOW_REDUCED`, `TASK_COMPLETED`, `REPLAN`.

1. Apply the event to the existing rows (no dataset copy). If it breaks an
   approved block (window gone / too short), that approval is voided and audited.
2. `run_and_persist(keep_approved=True)`: APPROVED blocks are frozen (their window
   and tasks leave the problem); windows of REJECTED blocks are withdrawn.
3. The previous assignment is passed to CP-SAT as a hint plus a stability reward
   (`W_STABILITY` per task kept in its window), so an event moves only what it must.
4. A `PlanVersion` row stores trigger, reason, actor, solver metadata and the diff
   (added / dropped / moved / unchanged). A `PLAN_LOCK` serializes plan writes.

## What-if simulation

`services/simulation.py` copies tasks and windows into plain in-memory objects,
applies the scenario (window extension, cancellations, gangs, traffic growth,
extra emergencies, objective preset, keep approved) and solves with CP-SAT in a
**deterministic** mode (interleaved search, deterministic time budget) so the
same input always gives the same plan. The baseline solve is cached (4 entries)
per data state. Nothing is written unless the user saves: then only a `Scenario`
row (parameters + metrics).

## Storage policy

| Data | Where | Growth control |
|---|---|---|
| Plan | `maintenance_blocks` / `block_tasks` (current plan only) | replaced on re-plan |
| Plan history | `plan_versions` (metadata + diff) | `PLAN_VERSION_RETENTION` (200) |
| Decisions | `audit_events` | `AUDIT_RETENTION` (10 000) |
| What-if | memory; `scenarios` on Save | `SCENARIO_LIMIT` (50) |
| Models | `ml_artifacts/*.joblib` (git-ignored, compressed) | overwritten, never versioned |
| Solver output | not stored (only metadata in `plan_versions`) | — |
| Logs | stdout; optional rotating `LOG_FILE` | `LOG_MAX_BYTES` × `LOG_BACKUPS` |
| Reports | streamed from memory | never written to disk |
| Tests | temp SQLite + temp model dir | deleted after the run |

## Frontend

React Router pages — **Dashboard** (KPIs + Chart.js), **AI Schedule**
(timeline/calendar, block explanation, approve/reject/approve-all, decision
history, plan version history, ⚡ live events), **Prioritized Tasks** (driver
bars, override with reason, revert to AI), **Corridor Map** (Leaflet),
**Planning Lab** (traffic forecast + what-if), **Reports** (PDF/Excel + model
info). No new frontend dependencies: charts reuse Chart.js.
The header's **Run AI Planner** button is a full reset + pipeline run.
