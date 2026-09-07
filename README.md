# 🚆 Automatic Block Planning System for Indian Railways

An **AI-powered maintenance-scheduling platform** that maximizes railway asset
availability by coordinating maintenance across three departments — **Engineering
(Permanent Way)**, **Signal & Telecom (S&T)** and **Traction Distribution (OHE)** —
into optimized, minimally-disruptive **traffic blocks**.

It ingests simulated departmental feeds (TMS / SMMS / TDMS / COA), assigns
**AI-driven priorities** with an explainable machine-learning model, and uses a
**Google OR-Tools constraint optimizer** to generate practical weekly and
monthly maintenance block plans.

---

## ✨ Features

| Module | What it does |
|---|---|
| **Data Integration** | Imports & normalizes TMS, SMMS, TDMS and COA feeds into one unified database. |
| **AI Prioritization** | XGBoost classifier assigns Critical/High/Medium/Low priority from defect severity, overdue days, asset criticality and traffic impact — **with an explanation for every task**. |
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
- **AI/ML:** Pandas, Scikit-learn, **XGBoost**
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
│   │   ├── api/                    # REST routes (pipeline, tasks, blocks, dashboard, reports)
│   │   ├── ml/                     # feature engineering + model training
│   │   └── services/               # data integration, AI prioritization,
│   │       │                       #   block planning, optimization, reports, dashboard
│   ├── data/
│   │   ├── generate_synthetic_data.py
│   │   └── raw/                    # generated sample CSVs (TMS/SMMS/TDMS/COA)
│   ├── scripts/seed_db.py          # one-shot bootstrap of the whole pipeline
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/                  # Dashboard, Schedule, Tasks, Map, Reports
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
pip install -r requirements-dev.txt   # optional: test deps (pytest)

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
2. **Model.** An **XGBoost** multiclass classifier learns to reproduce and
   generalize those labels (~0.89 test accuracy on the synthetic data). Each
   prediction is turned into a plain-English explanation using the record's own
   top drivers.
3. **Optimizer (OR-Tools CP-SAT).** Each block-requiring task gets an *optional
   interval* inside candidate maintenance windows on its corridor. A
   **cumulative** constraint models parallel gangs; the objective **maximizes
   AI-weighted coverage** while **minimizing the number of blocks** and
   **traffic disruption**, and **rewards combining multiple departments** into
   one possession.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detail.

---

## 🔌 Key API Endpoints (prefix `/api/v1`)

| Method | Path | Description |
|---|---|---|
| POST | `/pipeline/run` | Full pipeline: integrate → prioritize → optimize |
| GET | `/tasks` | Prioritized tasks (filter by dept/corridor/priority/status) |
| GET | `/blocks` | AI-generated maintenance blocks with tasks |
| GET | `/dashboard/kpis` | KPI card values |
| GET | `/dashboard/map` | Corridor status for the map |
| GET | `/reports/pdf?period=weekly` | PDF block plan |
| GET | `/reports/excel?period=weekly` | Excel block plan |

---

## 📊 Sample Dataset

`backend/data/raw/` contains ready-made CSVs. Regenerate anytime:
```bash
python backend/data/generate_synthetic_data.py --seed 42 --horizon 45 --plan-days 7
```
- `tms_track_defects.csv` — track/permanent-way defects
- `smms_signal_maintenance.csv` — signalling & telecom
- `tdms_electrical_maintenance.csv` — OHE / traction
- `coa_timetable.csv` + `coa_maintenance_windows.csv` — timetable & granted windows
- `master_stations.csv` — corridor/station master

---

## 📝 Notes

- The default database is **SQLite** so the stack runs with no external services.
  Point `DATABASE_URL` at PostgreSQL for production (schema is identical).
- The optimizer has a configurable time limit (`OPT_TIME_LIMIT_SECONDS`, default
  20s) — it returns the best feasible plan found within the budget.
