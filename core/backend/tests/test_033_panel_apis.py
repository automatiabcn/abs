"""033 Modul E + F + H — panel tools / cascade / pipeline endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.api.auth import current_admin
from app.db.models import CustomerAuditEntry
from app.db.session import get_engine
from app.main import app


@pytest.fixture(autouse=True)
def _signed_in():
    """These routes are the operator's, so the caller signs in as one.

    They used to answer anybody. That meant a stranger who knew a customer's URL
    could read the whole tool catalogue, and — through `/panel/cascade/recent` —
    which providers that company uses and a timestamp for every tool call it has
    made. The panel pages in front of these routes were behind a login the whole
    time, which is how it went unnoticed.

    Note what this fixture does *not* change: the contracts below. Only the door.
    `test_panel_endpoints_do_not_leak_license_jti` still matters — a signed-in
    operator has no business seeing another tenant's licence id either.
    """
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    yield
    app.dependency_overrides.pop(current_admin, None)


# ---------- E: tool browser ----------


def test_tool_browser_returns_total_and_categories(client):
    r = client.get("/v1/panel/tools")
    assert r.status_code == 200
    body = r.json()
    # 120 default — preview_patch + apply_patch gated off the MCP surface
    # (ABS_MCP_EXPOSE_PATCH_TOOLS, default off; arbitrary file read/write).
    assert body["total"] >= 120
    assert body["filtered_count"] == body["total"]
    assert isinstance(body["category_counts"], dict)
    assert len(body["category_counts"]) >= 5
    sample = body["tools"][0]
    for k in ("name", "description", "category", "input_schema"):
        assert k in sample


def test_tool_browser_category_filter_narrows_results(client):
    r = client.get("/v1/panel/tools?category=admin")
    body = r.json()
    assert body["filtered_count"] >= 1
    for t in body["tools"]:
        assert t["category"] == "admin"


def test_tool_browser_results_alphabetical_within_category(client):
    body = client.get("/v1/panel/tools?category=provider").json()
    names = [t["name"] for t in body["tools"]]
    assert names == sorted(names)


def test_tool_browser_includes_input_schema_summary(client):
    body = client.get("/v1/panel/tools").json()
    sample = body["tools"][0]
    assert "required" in sample["input_schema"]
    assert "properties" in sample["input_schema"]


# ---------- F: cascade visualiser ----------


def _seed_cascade_audit(jti: str = "demo_cascade_jti") -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        for i in range(3):
            db.add(
                CustomerAuditEntry(
                    license_jti=jti,
                    action="tool_call",
                    resource=["ask_groq_fast", "news_digest", "qual_code"][i],
                    ts=now - timedelta(minutes=i),
                )
            )
        db.commit()


def test_cascade_recent_returns_count_and_flows(client):
    _seed_cascade_audit()
    r = client.get("/v1/panel/cascade/recent?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 3
    assert isinstance(body["flows"], list)


def test_cascade_recent_each_flow_has_required_fields(client):
    _seed_cascade_audit("demo_cascade_jti2")
    body = client.get("/v1/panel/cascade/recent").json()
    sample = body["flows"][0]
    for k in ("ts", "tool", "cascade_path", "winner", "total_latency_ms"):
        assert k in sample


def test_cascade_recent_respects_limit(client):
    _seed_cascade_audit("demo_cascade_limit")
    body = client.get("/v1/panel/cascade/recent?limit=2").json()
    assert len(body["flows"]) <= 2


def test_cascade_providers_seen_is_sorted_unique(client):
    _seed_cascade_audit("demo_cascade_providers")
    body = client.get("/v1/panel/cascade/recent").json()
    seen = body["providers_seen"]
    assert seen == sorted(set(seen))


def test_panel_endpoints_do_not_leak_license_jti(client):
    """/v1/panel/* is unauthenticated; it must NOT expose the per-customer
    license JTI (a token identifier) in its activity flows. tool + ts only."""
    _seed_cascade_audit("secret_jti_must_not_leak")
    casc = client.get("/v1/panel/cascade/recent").json()
    assert casc["flows"], "expected seeded flows"
    for f in casc["flows"]:
        assert "license_jti" not in f, f
        assert "tool" in f and "ts" in f
    # pipeline endpoint shares the same audit source + leak surface.
    with Session(get_engine()) as db:
        db.add(
            CustomerAuditEntry(
                license_jti="secret_jti_must_not_leak",
                action="tool_call",
                resource="qual_code",
                ts=datetime.now(timezone.utc),
            )
        )
        db.commit()
    pipe = client.get("/v1/panel/pipeline/recent").json()
    assert pipe.get("pipeline_runs"), "expected seeded pipeline runs"
    for f in pipe["pipeline_runs"]:
        assert "license_jti" not in f, f
        assert "tool" in f


# ---------- H: quality pipeline viewer ----------


def _seed_pipeline_audit() -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        for i, tool in enumerate(("qual_code", "qual_tr", "qual_translate")):
            db.add(
                CustomerAuditEntry(
                    license_jti="demo_pipeline_jti",
                    action="tool_call",
                    resource=tool,
                    ts=now - timedelta(minutes=i),
                )
            )
        db.commit()


def test_pipeline_recent_returns_qual_runs_only(client):
    _seed_pipeline_audit()
    r = client.get("/v1/panel/pipeline/recent?limit=10")
    body = r.json()
    assert body["count"] >= 3
    for run in body["pipeline_runs"]:
        assert run["tool"].startswith("qual_")


def test_pipeline_recent_each_run_has_three_steps(client):
    _seed_pipeline_audit()
    body = client.get("/v1/panel/pipeline/recent").json()
    for run in body["pipeline_runs"]:
        assert len(run["steps"]) == 3
        for step in run["steps"]:
            for k in ("role", "model", "latency_ms"):
                assert k in step


def test_pipeline_recent_excludes_non_qual_tools(client):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            CustomerAuditEntry(
                license_jti="demo_pipeline_jti_filter",
                action="tool_call",
                resource="ask_groq_fast",
                ts=now,
            )
        )
        db.commit()
    body = client.get("/v1/panel/pipeline/recent").json()
    for run in body["pipeline_runs"]:
        assert run["tool"] != "ask_groq_fast"


def test_pipeline_recent_respects_limit(client):
    _seed_pipeline_audit()
    body = client.get("/v1/panel/pipeline/recent?limit=1").json()
    assert len(body["pipeline_runs"]) <= 1
