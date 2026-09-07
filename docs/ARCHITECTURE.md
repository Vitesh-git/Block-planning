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
                    │  AI Prioritization     │  XGBoost + explanation
                    │  (ml/ + services/ai_)  │  → Critical/High/Med/Low
                    └───────────┬────────────┘
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
- **MaintenanceBlock** 1─* **BlockTask** *─1 **MaintenanceTask** — optimizer output.

## AI prioritization

Features: `severity`, `asset_criticality`, `overdue_days`, `traffic_gmt`,
`estimated_duration_min`, `requires_traffic_block`, `gang_size`, engineered
`sla_pressure` (`log1p(overdue)·severity`) and `traffic_impact`
(`traffic·(1+block)`), plus one-hot department.

Target labels come from a domain-weighted **priority index** (0.32·severity +
0.24·criticality + 0.20·overdue + 0.16·traffic + 0.08·block), binned into four
ordered classes. XGBoost learns and generalizes this policy; explanations are
produced by combining global feature importances with each record's normalized
feature values to surface its top 3 drivers.

## Optimization (OR-Tools CP-SAT)

**Decision variables**
- `present[t,w] ∈ {0,1}` — task `t` placed in window `w` (same corridor only).
- Optional interval `iv[t,w]` of duration `dur(t)` inside `[0, len(w)]`.
- `used[w]` — a block is opened for window `w`.

**Constraints**
- Each task placed in **at most one** window: `Σ_w present[t,w] ≤ 1`.
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

`disruption_w` favours **night blocks** and penalizes possessions on
high-traffic corridors. The result: fewer line possessions, high-priority work
done first, and Engineering/S&T/Traction work combined into shared blocks
wherever feasible.

## Frontend

React Router pages — **Dashboard** (KPIs + Chart.js), **AI Schedule**
(weekly/monthly calendar + block detail), **Prioritized Tasks** (with
explanations), **Corridor Map** (Leaflet), **Reports** (PDF/Excel + model info).
The header's **Run AI Planner** button triggers the full backend pipeline live.
