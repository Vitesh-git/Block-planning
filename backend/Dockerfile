FROM python:3.11-slim

WORKDIR /app

# All pinned deps (OR-Tools, pandas, scikit-learn, psycopg2-binary) ship as
# binary wheels for this image, so no compiler / OS packages are installed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install -r requirements.txt

# .dockerignore keeps .venv, tests, caches and local DB files out of the image
COPY . .

EXPOSE 8000
# Render (and most PaaS) inject $PORT; fall back to 8000 for local runs.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
