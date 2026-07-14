"""Detailed health endpoint."""

from __future__ import annotations


def test_health_full_returns_overall_and_checks(client):
    r = client.get("/v1/health/full")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert "checks" in body
    assert isinstance(body["checks"], list)
    names = {c["name"] for c in body["checks"]}
    assert {
        "database",
        "vault",
        "providers",
        "rag",
        "mcp",
        "email",
        "data_dir",
    }.issubset(names)


def test_health_full_database_check_passes(client):
    r = client.get("/v1/health/full")
    db_check = next(c for c in r.json()["checks"] if c["name"] == "database")
    assert db_check["ok"] is True
    assert "engine" in db_check["detail"]


def test_health_full_mcp_check_reports_tool_count(client):
    r = client.get("/v1/health/full")
    mcp_check = next(c for c in r.json()["checks"] if c["name"] == "mcp")
    assert mcp_check["ok"] is True
    count = mcp_check["detail"]["registered_count"]
    assert count >= 100, f"too few MCP tools: {count}"
