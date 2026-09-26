"""Test isolation: every test session uses a throw-away SQLite file and model
directory, so running pytest never touches the developer database or the
real ml_artifacts. The temp directory is removed when the session ends."""

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="rbp-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/")
os.environ["MODEL_DIR"] = os.path.join(_TMP, "ml_artifacts")
os.environ.setdefault("OPT_TIME_LIMIT_SECONDS", "5")
os.environ.setdefault("SIM_TIME_LIMIT_SECONDS", "4")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/v1/pipeline/run", json={"reset": True, "time_limit_s": 5, "actor": "pytest"})
        assert r.status_code == 200, r.text
        yield c


def pytest_sessionfinish(session, exitstatus):
    try:
        from app.core.database import engine

        engine.dispose()  # release the SQLite file (needed on Windows)
    except Exception:
        pass
    shutil.rmtree(_TMP, ignore_errors=True)
