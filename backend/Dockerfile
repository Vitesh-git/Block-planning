FROM python:3.11-slim

WORKDIR /app

# System deps for building some wheels (ortools/xgboost are wheels; keep slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Render (and most PaaS) inject $PORT; fall back to 8000 for local runs.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
