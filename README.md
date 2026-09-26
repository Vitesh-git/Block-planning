# 🚆 Automatic Block Planning System for Indian Railways

An **AI-powered maintenance-scheduling platform** that maximizes railway asset
availability by coordinating maintenance across three departments — **Engineering
(Permanent Way)**, **Signal & Telecom (S&T)** and **Traction Distribution (OHE)** —
into optimized, minimally-disruptive **traffic blocks**.

It ingests simulated departmental feeds (TMS / SMMS / TDMS / COA), assigns
**AI-driven priorities** with an explainable machine-learning model, forecasts
**passenger + goods traffic**, and uses a **Google OR-Tools constraint
optimizer** to generate — and re-plan live — practical weekly and monthly
maintenance block plans that a controller approves.

---

## ✨ Features

| Module | What it does |
|---|---|
| **Data Integration** | Imports & normalizes TMS, SMMS, TDMS and COA feeds into one unified database. |
| **AI Maintenance Priority** | Gradient-boosted classifier (scikit-learn) assigns Critical/High/Medium/Low plus a 0–1 expected-priority score, with per-task driver bars and a transparent safety rule (severity-5 on a critical asset is never below High). |
| **Train + Goods Traffic Forecasting** | Poisson gradient-boosted model forecasts hourly passenger and goods trains per corridor (goods are not timetabled); every window is priced by the trains it would hold. |
| **Explainable AI + Human Approval** | "Why this block" for every possession, approve / reject (reason required) / approve-all, AI-vs-controller priority overrides with reasons, full audit trail. |
| **What-If Simulation** | Change window length, cancel windows, gangs, traffic growth, emergencies or objective; the optimizer runs in memory and compares against the current settings. Saved only on request. |
| **Dynamic Real-Time Rescheduling** | Live events (emergency defect, window cancelled / shortened, re-plan) re-optimize around approved blocks with minimal churn; each change is a lightweight plan version with a diff. |
| **Automatic Block Planning** | Groups tasks by corridor & location and combines multi-department work into shared blocks. |
| **Optimization Engine** | OR-Tools CP-SAT scheduler: no overlapping possessions per corridor, high-priority first, disruption minimized, multi-department coordination, fewest blocks. |
| **Dashboard** | KPI cards, weekly/monthly calendars, Leaflet corridor map, AI schedule, Chart.js analytics. |
| **Reports** | Downloadable **PDF** and **Excel** weekly/monthly block plans. |
| **Sample Dataset** | Realistic synthetic data generator for all four source systems. |

---

## 🧱 Tech Stack

- **Frontend:** React 18 + Vite + Tailwind CSS + Chart.js + React-Leaflet
- **Backend:** FastAPI (Python) + SQLAlchemy
- **Database:** PostgreSQL (production) — **SQLite fallback** for zero-setup dev
- **AI/ML:** Pandas, **scikit-learn** (HistGradientBoosting classifier + Poisson regressor)
- **Optimization:** **Google OR-Tools** (CP-SAT)
- **Reports:** ReportLab (PDF), OpenPyXL (Excel)

---

## 📁 Project Structure

```
railway-block-planning/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint
│   │   ├── core/                   # config + database (Postgres/SQLite)
│   │   ├── models/                 # SQLAlchemy schema
│   │   ├── schemas/                # Pydantic I/O models
│   │   ├── api/                    # REST routes (pipeline, tasks, blocks, dashboard,
│   │   │                           #   reports, planning = forecast/simulate/reschedule/audit)
│   │   ├── ml/                     # feature engineering + priority-model training
│   │   └── services/               # data integration, AI prioritization, traffic forecast,
│   │       │                       #   optimization, governance (explain/approve/audit),
│   │       │                       #   simulation, rescheduling, reports, dashboard
│   ├── data/
│   │   ├── generate_synthetic_data.py
│   │   └── raw/                    # generated sample CSVs (TMS/SMMS/TDMS/COA)
│   ├── scripts/seed_db.py          # one-shot bootstrap of the whole pipeline
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/                  # Dashboard, Schedule, Tasks, Map, Planning Lab, Reports
│   │   ├── components/             # Layout, KPI cards, charts, badges
│   │   └── api/client.js           # axios API client
│   └── package.json
├── docker-compose.yml              # Postgres + backend + frontend
└── docs/ARCHITECTURE.md
```

---

## 🚀 Quick Start

### Option A — Zero-setup (SQLite, recommended to try it)

**1. Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional: test deps (pytest, httpx)
pytest -q                             # uses a temporary database, never your dev DB

# Generate sample data, train the model, run the optimizer, seed the DB:
python data/generate_synthetic_data.py
python -m scripts.seed_db


# Start the API:
python -m uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

**2. Frontend**
```bash
cd frontend
npm install
npm run dev
```
App: http://localhost:5173  (the Vite dev server proxies `/api` to the backend)

Click **"Run AI Planner"** in the header to (re)run the full pipeline live.

### Option B — PostgreSQL

Set `DATABASE_URL` before seeding/serving:
```bash
export DATABASE_URL="postgresql+psycopg2://railway:railway@localhost:5432/railway_bps"
python -m scripts.seed_db
python -m uvicorn app.main:app --port 8000
```

### Option C — Docker Compose (Postgres + API + web)
```bash
docker compose up --build
```

---

## 🧠 How the AI + Optimization works

1. **Priority index → labels.** A transparent, domain-weighted index (severity,
   asset criticality, overdue days, corridor traffic, block requirement) defines
   ground-truth Critical/High/Medium/Low labels.
2. **Model.** A scikit-learn **HistGradientBoosting** classifier learns to
   reproduce and generalize those labels (~0.89 hold-out / ~0.91 4-fold CV
   accuracy on the synthetic data). Each task gets its own drivers (model-based
   occlusion against a typical task) and a plain-English explanation.
3. **Traffic forecast.** A Poisson gradient-boosted regressor predicts hourly
   passenger and goods trains per corridor; timetabled passenger trains override
   the passenger forecast. Window disruption = forecast trains held, goods
   weighted 0.7.
4. **Optimizer (OR-Tools CP-SAT).** Each block-requiring task gets an *optional
   interval* inside candidate maintenance windows on its corridor (only windows
   long enough for the whole job). A **cumulative** constraint models parallel
   gangs; the objective **maximizes AI-weighted coverage** while **minimizing the
   number of blocks** and **forecast traffic disruption**, and **rewards combining
   multiple departments** into one possession. On a live event, approved blocks
   are frozen and a stability bonus keeps the rest of the plan where it was.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detail.

---

## 🔌 Key API Endpoints (prefix `/api/v1`)

| Method | Path | Description |
|---|---|---|
| POST | `/pipeline/run` | Full reset + pipeline: integrate → prioritize → forecast → optimize |
| GET | `/tasks` | Prioritized tasks (filter by dept/corridor/priority/status) |
| GET | `/blocks` | AI-generated maintenance blocks with tasks |
| GET | `/dashboard/kpis` | KPI card values |
| GET | `/dashboard/map` | Corridor status for the map |
| GET | `/reports/pdf?period=weekly` | PDF block plan |
| GET | `/reports/excel?period=weekly` | Excel block plan |
| PATCH | `/blocks/{id}` | Approve / reject (note required) / reset a block |
| POST | `/blocks/approve-all` | Approve every pending block |
| PATCH | `/tasks/{id}` | Status, priority override (reason required) or `revert_to_ai` |
| GET | `/forecast/traffic?corridor_id=&days=7` | Passenger + goods outlook and window impact |
| POST | `/simulate` | What-if scenario (in memory; `save: true` stores params + metrics) |
| GET/DELETE | `/scenarios` | Saved scenarios |
| POST | `/reschedule` | Live event → incremental re-plan (new plan version) |
| GET | `/plan/versions` | Plan version history with solver metadata and diffs |
| GET | `/audit` | Audit trail (filter by `entity_type`, `entity_id`) |

---

## 📊 Sample Dataset

`backend/data/raw/` contains ready-made CSVs. Regenerate anytime:
```bash
python backend/data/generate_synthetic_data.py --seed 42 --horizon 45 --plan-days 7
```
- `tms_track_defects.csv` — track/permanent-way defects
- `smms_signal_maintenance.csv` — signalling & telecom
- `tdms_electrical_maintenance.csv` — OHE / traction
- `coa_timetable.csv` — 7 days of actual running (passenger + goods) before the
  plan, then the timetabled passenger trains for the plan week
- `coa_maintenance_windows.csv` — granted windows
- `master_stations.csv` — corridor/station master

---

## 📝 Notes

- The default database is **SQLite** so the stack runs with no external services.
  Point `DATABASE_URL` at PostgreSQL for production (schema is identical).
- The optimizer has a configurable time limit (`OPT_TIME_LIMIT_SECONDS`, default
  20s) — it returns the best feasible plan found within the budget. What-if runs
  use `SIM_TIME_LIMIT_SECONDS` (default 8s) in a reproducible deterministic mode.
- **Header "Run AI Planner" = full reset** (reloads data, clears approvals and plan
  history). For live changes use **⚡ Live event**, which keeps approved blocks.
- There is no login: the "Acting as" name in the sidebar is recorded on approvals,
  overrides and events. Put real authentication in front of the API before
  production use.

## 💾 Storage footprint

Kept deliberately small (see `docs/ARCHITECTURE.md` → *Storage policy*):

- Model artifacts (git-ignored, regenerated): `priority_model.joblib` ≈ 0.2 MB,
  `traffic_forecast.joblib` ≈ 25 KB, `model_meta.json` ≈ 6 KB.
- What-if runs are in memory; a scenario row is written only on **Save**.
- Re-plans store one small `plan_versions` row (solver metadata + diff), never a
  copy of the plan or the CP-SAT log. Retention caps: `PLAN_VERSION_RETENTION`
  (200), `AUDIT_RETENTION` (10 000 rows), `SCENARIO_LIMIT` (50).
- Logs go to stdout; set `LOG_FILE` for a rotating file capped at
  `LOG_MAX_BYTES` × (`LOG_BACKUPS` + 1).

  WEBSITE LINK::
  block-planning.vercel.app
