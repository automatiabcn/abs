"""HITL approval + panel session → OAuth principal bridge tests."""

from __future__ import annotations

import time

import pytest

from app.workflow_v10.approval import (
    ApprovalLedger,
    PanelSessionPrincipal,
    panel_session_to_principal,
)


# ---- panel session bridge ---------------------------------------------


def test_panel_session_to_principal_roundtrip() -> None:
    def lookup(sid):  # noqa: ANN001
        return {"subject": "alice", "tenant_id": "t1", "roles": "member,owner"}

    p = panel_session_to_principal(session_id="abc", session_lookup=lookup)
    assert isinstance(p, PanelSessionPrincipal)
    assert p.subject == "alice"
    assert p.tenant_id == "t1"
    assert p.roles == ["member", "owner"]


def test_panel_session_missing_session_raises() -> None:
    with pytest.raises(KeyError):
        panel_session_to_principal(session_id="x", session_lookup=lambda s: None)


def test_panel_session_invalid_payload_raises() -> None:
    with pytest.raises(ValueError):
        panel_session_to_principal(
            session_id="x",
            session_lookup=lambda s: {"subject": "alice", "tenant_id": ""},
        )


def test_panel_session_accepts_list_roles() -> None:
    p = panel_session_to_principal(
        session_id="x",
        session_lookup=lambda s: {
            "subject": "u",
            "tenant_id": "t",
            "roles": ["admin"],
        },
    )
    assert p.roles == ["admin"]


def test_panel_session_requires_session_id() -> None:
    with pytest.raises(ValueError):
        panel_session_to_principal(session_id="", session_lookup=lambda s: {})


# ---- approval ledger --------------------------------------------------


def test_request_and_decide_round_trip() -> None:
    ledger = ApprovalLedger()
    req = ledger.request(
        tenant_id="t1",
        subject="rag.ingest",
        requester="alice",
        payload={"doc_id": "d1"},
    )
    assert req.request_id
    dec = ledger.decide(
        request_id=req.request_id,
        approved=True,
        decided_by="bob",
        note="lgtm",
    )
    assert dec.approved is True
    assert ledger.get_decision(req.request_id).decided_by == "bob"


def test_decide_unknown_raises() -> None:
    with pytest.raises(KeyError):
        ApprovalLedger().decide(request_id="nope", approved=False, decided_by="x")


def test_request_requires_tenant_and_requester() -> None:
    with pytest.raises(ValueError):
        ApprovalLedger().request(
            tenant_id="",
            subject="x",
            requester="alice",
            payload={},
        )


def test_is_overdue_true_after_threshold() -> None:
    ledger = ApprovalLedger()
    req = ledger.request(
        tenant_id="t1",
        subject="email.send",
        requester="alice",
        payload={},
        auto_escalate_after_seconds=1,
    )
    assert ledger.is_overdue(req.request_id, now=time.time()) is False
    assert ledger.is_overdue(req.request_id, now=time.time() + 5) is True


def test_is_overdue_false_after_decision() -> None:
    ledger = ApprovalLedger()
    req = ledger.request(
        tenant_id="t1",
        subject="email.send",
        requester="alice",
        payload={},
        auto_escalate_after_seconds=1,
    )
    ledger.decide(request_id=req.request_id, approved=True, decided_by="bob")
    assert ledger.is_overdue(req.request_id, now=time.time() + 1000) is False
