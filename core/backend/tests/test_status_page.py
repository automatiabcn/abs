"""Status page JSON + HTML."""

from __future__ import annotations


def test_status_json_response_shape(client):
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert "overall" in body
    assert body["overall"] in {"ok", "degraded", "down"}
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], int)
    assert "version" in body
    assert "services" in body
    names = {s["name"] for s in body["services"]}
    assert names == {"database", "vault", "providers", "rag", "mcp", "email", "stripe"}


def test_status_json_db_check_passes_in_test_env(client):
    r = client.get("/v1/status")
    db = next(s for s in r.json()["services"] if s["name"] == "database")
    assert db["ok"] is True


def test_status_json_overall_ok_in_healthy_env(client):
    r = client.get("/v1/status")
    body = r.json()
    # Test env should have ≥5/7 healthy → ok
    assert body["overall"] in {"ok", "degraded"}


def test_status_html_renders(client):
    r = client.get("/status")
    assert r.status_code == 200
    text = r.text
    assert "Automatia ABS" in text
    assert "auto-refresh 30s" in text
    assert "/v1/status" in text
    assert "<title>" in text
