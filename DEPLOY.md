# Deployment guide

Two parts: **backend on Render** (real Python server) + **frontend on Vercel**
(static Vite build). They are connected by one environment variable.

## 0. Push the repo to GitHub
From this folder (the one containing `backend/` and `frontend/`):

    git add -A
    git commit -m "Add deploy config"
    git branch -M main
    git remote add origin https://github.com/<you>/railway-block-planning.git
    git push -u origin main

## 1. Backend → Render  (do this first, you need its URL)
1. Go to https://render.com → sign in with GitHub.
2. **New + → Blueprint** → pick this repo. Render reads `render.yaml` and
   creates the `railway-bps-api` Docker service (free plan).
   - (Manual alternative: New + → **Web Service** → repo → Root Directory
     `backend`, Runtime **Docker**, Health Check Path `/health`.)
3. First build takes a few minutes (it installs OR-Tools + XGBoost). When it's
   live you get a URL like `https://railway-bps-api.onrender.com`.
4. Test it: open `https://railway-bps-api.onrender.com/health` → `{"status":"healthy"}`.

Notes:
- The database is created automatically; click **Run AI Planner** in the app to
  load data, train the model, and generate the plan.
- Free instances sleep after inactivity, so the first request may take ~30s.

## 2. Frontend → Vercel
1. Go to https://vercel.com → **Add New… → Project** → import this repo.
2. **Root Directory:** `frontend`   ·   **Framework Preset:** `Vite`
   (Build `npm run build`, Output `dist` — auto-filled.)
3. **Environment Variables** → add:
   - `VITE_API_BASE = https://railway-bps-api.onrender.com/api/v1`
     (your Render URL + `/api/v1`)
4. **Deploy.** You get a URL like `https://railway-block-planning.vercel.app`.

## 3. Lock down CORS (optional, recommended)
In Render → your service → **Environment** → set
`CORS_ORIGINS = https://railway-block-planning.vercel.app` (your Vercel URL),
then save (it redeploys). This replaces the demo `*`.

## Done
Open the Vercel URL → **Generate Optimized Plan** → the plan appears.
