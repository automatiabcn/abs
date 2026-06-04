"""Observability round — /healthz is a real DB readiness probe, not a stub.

The container/orchestrator healthcheck calls /healthz. A shallow always-"ok"
body let docker/k8s keep a backend with a dead database marked healthy. These
tests pin the readiness contract: 200 + db:up when the DB answers, 503 +
db:down when the SELECT 1 ping fails, and that the ping swallows DB errors
into a clean False (never a 500).
"""

from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app


def test_healthz_ok_reports_db_up():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "abs-backend"
    assert body["db"] == "up"


def test_healthz_returns_503_when_db_not_ready(monkeypatch):
    # Patch the readiness seam (not get_engine globally — that would also break
    # the app's startup/lifespan, masking the route's own behaviour).
    monkeypatch.setattr(main_mod, "_healthz_db_ready", lambda: False)

    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"] == "down"


def test_db_ready_swallows_outage_into_false(monkeypatch):
    # Called directly (no TestClient → no lifespan), so making get_engine raise
    # exercises only the ping's try/except, proving it never propagates a 500.
    def _boom():
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(main_mod, "get_engine", _boom)
    assert main_mod._healthz_db_ready() is False
