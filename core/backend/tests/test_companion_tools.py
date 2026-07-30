# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Companion MCP tools — approvals + meetings for the editor's side panels.

Both surfaces existed only behind a panel cookie / OAuth JWT, so an editor
holding an ``abs_mcp_`` token could gate nothing and show no meeting record.
Tenant scoping comes from the caller's token, never from an argument.
"""

from __future__ import annotations

import asyncio
import json

import pytest

# Server first: it registers every tool module (see test_engine_panel_tools).
from app.mcp.server import mcp_server  # noqa: F401

from app.mcp.tools import companion_tools as ct


def _call(coro):
    return json.loads(asyncio.run(coro))


@pytest.fixture()
def as_tenant(monkeypatch):
    def _set(tenant: str, user: str = "alice"):
        monkeypatch.setattr(ct, "_caller", lambda: (tenant, user))

    return _set


def _seed_meeting(tenant: str, filename: str = "standup.m4a") -> int:
    import secrets

    from sqlmodel import Session

    from app.db.models import Meeting, MeetingSegment
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        m = Meeting(
            tenant_slug=tenant,
            filename=filename,
            duration_sec=90.0,
            speaker_count=2,
            status="done",
            summary="kısa özet",
            uploader_email="uploader@local",
            # Uploads are de-duplicated by audio fingerprint, so two seeded
            # meetings need distinct ones.
            audio_sha256=secrets.token_hex(16),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        db.add(
            MeetingSegment(
                meeting_id=m.id,
                speaker_id="spk_1",
                start_sec=0.0,
                end_sec=4.0,
                text="Yarın raporu ben göndereceğim.",
            )
        )
        db.commit()
        return int(m.id)


def test_meetings_list_is_scoped_to_the_calling_tenant(as_tenant):
    _seed_meeting("acme")
    _seed_meeting("globex", filename="other.m4a")

    as_tenant("acme")
    out = _call(ct.meetings_list())
    assert out["ok"] is True
    names = {m["filename"] for m in out["meetings"]}
    assert "standup.m4a" in names
    assert "other.m4a" not in names, "another tenant's meeting leaked into the panel"


def test_meeting_get_returns_transcript_and_action_items(as_tenant):
    meeting_id = _seed_meeting("acme2")
    as_tenant("acme2")
    out = _call(ct.meeting_get(meeting_id))
    assert out["ok"] is True
    assert out["summary"] == "kısa özet"
    assert out["segments"][0]["text"].startswith("Yarın raporu")
    # The Turkish first-person commitment is exactly what the extractor targets.
    assert out["action_items"], "an actionable line produced no action item"


def test_meeting_get_refuses_another_tenants_meeting(as_tenant):
    meeting_id = _seed_meeting("owner-corp")
    as_tenant("intruder-corp")
    out = _call(ct.meeting_get(meeting_id))
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_approvals_list_returns_the_queue_and_summary(as_tenant, monkeypatch):
    captured = {}

    def _fake_list(*, tenant_slug, status, limit):
        captured["tenant"] = tenant_slug
        captured["status"] = status
        return {"items": [{"id": 1, "risk": "high"}], "pending_total": 1}

    monkeypatch.setattr("app.approvals.service.list_approvals", _fake_list)
    as_tenant("acme3")
    out = _call(ct.approvals_list(status="pending"))
    assert out["ok"] is True
    assert out["pending_total"] == 1
    assert captured["tenant"] == "acme3", "tenant must come from the token"


def test_approvals_decide_passes_the_callers_identity(as_tenant, monkeypatch):
    seen = {}

    def _fake_decide(**kwargs):
        seen.update(kwargs)
        return {"id": 7, "status": "approved"}

    monkeypatch.setattr("app.approvals.service.decide_approval", _fake_decide)
    as_tenant("acme4", user="bob")
    out = _call(ct.approvals_decide(7, "approve", note="ok"))
    assert out["ok"] is True
    assert out["item"]["status"] == "approved"
    assert seen["tenant_slug"] == "acme4"
    assert "bob" in seen["decided_by"], "the audit trail must name who decided"


def test_approvals_decide_reports_an_already_decided_item(as_tenant, monkeypatch):
    monkeypatch.setattr(
        "app.approvals.service.decide_approval", lambda **_: None
    )
    as_tenant("acme5")
    out = _call(ct.approvals_decide(9, "approve"))
    assert out["ok"] is False
    assert out["error"] == "not_found_or_not_pending"


def test_approvals_decide_rejects_a_bad_decision(as_tenant, monkeypatch):
    def _raise(**_):
        raise ValueError("invalid decision: maybe")

    monkeypatch.setattr("app.approvals.service.decide_approval", _raise)
    as_tenant("acme6")
    out = _call(ct.approvals_decide(1, "maybe"))
    assert out["ok"] is False
    assert out["error"] == "invalid_decision"


@pytest.mark.parametrize(
    "name", ["approvals_list", "approvals_decide", "meetings_list", "meeting_get"]
)
def test_tools_are_registered(name):
    from app.mcp.server import mcp_server as srv

    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert name in names


def test_workflow_list_is_scoped_and_counts_steps(as_tenant):
    import json as _json

    from sqlmodel import Session

    from app.db.models import SavedWorkflow
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        db.add(
            SavedWorkflow(
                tenant_slug="wf-corp",
                name="nightly digest",
                definition_json=_json.dumps({"nodes": [{"id": "a"}, {"id": "b"}]}),
                created_by="alice",
            )
        )
        db.add(
            SavedWorkflow(
                tenant_slug="other-corp",
                name="theirs",
                definition_json=_json.dumps({"nodes": []}),
                created_by="bob",
            )
        )
        # A definition we cannot read has an UNKNOWN step count, not zero.
        db.add(
            SavedWorkflow(
                tenant_slug="wf-corp",
                name="corrupt",
                definition_json="{not json",
                created_by="alice",
            )
        )
        db.commit()

    as_tenant("wf-corp")
    out = _call(ct.workflow_list())
    assert out["ok"] is True
    names = {w["name"]: w for w in out["workflows"]}
    assert "theirs" not in names, "another tenant's workflow leaked into the panel"
    assert names["nightly digest"]["steps"] == 2
    assert names["corrupt"]["steps"] is None, "unreadable ≠ empty"
