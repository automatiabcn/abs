# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Approval Center (DB) — log agent run, open approval, decide; tenant-scoped."""

from __future__ import annotations

import pytest

from app.agents.runtime import AgentResult, Evidence
from app.approvals import service


def _result(
    agent_id: str = "outbound_draft", risk: str = "high", approval: bool = True
) -> AgentResult:
    return AgentResult(
        agent_id=agent_id,
        output_kind="outbound_draft",
        summary="taslak hazır",
        payload={"message": "Merhaba, teklifimiz ektedir."},
        evidence=[Evidence("rag", "fiyat.pdf", "fiyat aralığı...")],
        confidence=0.8,
        recommended_action="email gönder",
        risk=risk,
        requires_approval=approval,
        provider="cloudflare",
        elapsed_ms=12,
    )


def test_log_run_create_and_decide() -> None:
    res = _result()
    run_id = service.log_agent_run(
        res, tenant_slug="tA", actor="a@x.io", task="taslak yaz"
    )
    assert isinstance(run_id, int) and run_id > 0

    item = service.create_approval_from_result(
        res,
        tenant_slug="tA",
        requester="a@x.io",
        agent_run_id=run_id,
        target_company="Kaya İnşaat",
        channel="email",
        consent_status="opt-in",
    )
    assert item["status"] == "pending"
    assert item["risk"] == "high"
    assert item["proposed_message"].startswith("Merhaba")
    assert item["evidence"][0]["kind"] == "rag"
    assert item["agent_run_id"] == run_id

    listed = service.list_approvals(tenant_slug="tA")
    assert listed["pending_total"] >= 1
    assert listed["by_risk"]["high"] >= 1

    got = service.get_approval(tenant_slug="tA", item_id=item["id"])
    assert got is not None and got["id"] == item["id"]

    decided = service.decide_approval(
        tenant_slug="tA",
        item_id=item["id"],
        decision="approve",
        decided_by="boss@x.io",
        note="ok",
    )
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "boss@x.io"
    assert decided["outcome"] == "ok"


def test_claim_pending_transition_wins_exactly_once() -> None:
    """Concurrency guard — the outbound action behind an approval must fire at
    most once. Two decides racing on the same pending item both read
    status='pending' before either commits; the atomic claim lets exactly one
    win. A plain read-then-write gate would fire the action twice."""
    from sqlmodel import Session

    from app.db.session import get_engine

    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tClaim", actor="")
    item = service.create_approval_from_result(
        res,
        tenant_slug="tClaim",
        requester="",
        agent_run_id=rid,
    )
    iid = item["id"]
    with Session(get_engine()) as db:  # first claimant wins
        assert (
            service._claim_pending_transition(
                db, item_id=iid, tenant_slug="tClaim", new_status="approved"
            )
            is True
        )
        db.commit()
    with Session(get_engine()) as db:  # second sees non-pending → loses
        assert (
            service._claim_pending_transition(
                db, item_id=iid, tenant_slug="tClaim", new_status="approved"
            )
            is False
        )


def test_decide_fires_action_at_most_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deciding an item twice sends once — and the second decision is refused."""
    import app.actions as actions_mod

    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tFire", actor="")
    item = service.create_approval_from_result(
        res,
        tenant_slug="tFire",
        requester="",
        agent_run_id=rid,
        target_company="Kaya",
        channel="email",
        consent_status="opt-in",
    )
    calls = {"n": 0}

    def _fake_exec(row, *, tenant_slug):  # noqa: ANN001
        calls["n"] += 1
        return {"status": "sent", "reason": "delivered to a@x.io"}

    monkeypatch.setattr(actions_mod, "execute_for_approval", _fake_exec)
    service.decide_approval(
        tenant_slug="tFire",
        item_id=item["id"],
        decision="approve",
        decided_by="b@x.io",
    )
    with pytest.raises(service.AlreadyDecided):
        service.decide_approval(
            tenant_slug="tFire",
            item_id=item["id"],
            decision="approve",
            decided_by="b@x.io",
        )
    assert calls["n"] == 1


def test_a_rejection_cannot_be_rewritten_into_an_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decision is a record of what a person chose, and it stands.

    The send was never the risk here — nothing re-fires. The risk was the row:
    a re-decide used to overwrite `status` and report success, so an item a
    person had rejected could end up reading "approved", with a timestamp and a
    name against it, and nothing actually sent. Whoever read that row later
    would believe a message went out. The refusal has to survive being asked
    again.
    """
    import app.actions as actions_mod

    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tKeep", actor="")
    item = service.create_approval_from_result(
        res,
        tenant_slug="tKeep",
        requester="",
        agent_run_id=rid,
        target_company="Kaya",
        channel="email",
        consent_status="opt-in",
    )
    calls = {"n": 0}

    def _fake_exec(row, *, tenant_slug):  # noqa: ANN001
        calls["n"] += 1
        return {"status": "sent", "reason": "delivered to a@x.io"}

    monkeypatch.setattr(actions_mod, "execute_for_approval", _fake_exec)

    rejected = service.decide_approval(
        tenant_slug="tKeep",
        item_id=item["id"],
        decision="reject",
        decided_by="boss@x.io",
    )
    assert rejected["status"] == "rejected"

    with pytest.raises(service.AlreadyDecided):
        service.decide_approval(
            tenant_slug="tKeep",
            item_id=item["id"],
            decision="approve",
            decided_by="someone@x.io",
        )

    still = service.get_approval(tenant_slug="tKeep", item_id=item["id"])
    assert still["status"] == "rejected", "a rejection was rewritten into an approval"
    assert still["decided_by"] == "boss@x.io", "the record named the wrong person"
    assert calls["n"] == 0, "a rejected action was sent"


def test_accept_rate_is_none_until_a_decision_exists() -> None:
    """3rd-eye audit — with no decided items the accept rate is unknown, not a
    fabricated 91%. It must be None (panel shows "—") and only become a real
    number once at least one item is decided."""
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tRate", actor="")
    item = service.create_approval_from_result(
        res,
        tenant_slug="tRate",
        requester="",
        agent_run_id=rid,
    )
    fresh = service.list_approvals(tenant_slug="tRate")
    assert fresh["tier_stats"]["accept_rate"] is None  # was a hardcoded 91

    service.decide_approval(
        tenant_slug="tRate",
        item_id=item["id"],
        decision="approve",
        decided_by="boss@x.io",
    )
    after = service.list_approvals(tenant_slug="tRate")
    assert after["tier_stats"]["accept_rate"] == 100  # 1/1 approved


def test_approval_tenant_isolation() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tX", actor="")
    item = service.create_approval_from_result(
        res, tenant_slug="tX", requester="", agent_run_id=rid
    )
    # other tenant cannot read or decide it (application-layer scope)
    assert service.get_approval(tenant_slug="tY", item_id=item["id"]) is None
    assert (
        service.decide_approval(
            tenant_slug="tY", item_id=item["id"], decision="approve", decided_by="x"
        )
        is None
    )


def test_invalid_decision_raises() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tZ", actor="")
    item = service.create_approval_from_result(
        res, tenant_slug="tZ", requester="", agent_run_id=rid
    )
    with pytest.raises(ValueError):
        service.decide_approval(
            tenant_slug="tZ", item_id=item["id"], decision="bogus", decided_by="x"
        )


def test_recent_agent_runs_tenant_scoped() -> None:
    service.log_agent_run(
        _result(agent_id="knowledge_base", risk="low", approval=False),
        tenant_slug="tR",
        actor="a@x.io",
        task="soru",
    )
    runs = service.recent_agent_runs(tenant_slug="tR", limit=10)
    assert len(runs) >= 1
    assert runs[0]["agent_id"] == "knowledge_base"  # newest first
    # isolation: a fresh tenant sees none of tR's runs
    assert service.recent_agent_runs(tenant_slug="tR-empty-xyz") == []


def test_edit_updates_message() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tE", actor="")
    item = service.create_approval_from_result(
        res, tenant_slug="tE", requester="", agent_run_id=rid
    )
    edited = service.decide_approval(
        tenant_slug="tE",
        item_id=item["id"],
        decision="edit",
        decided_by="ed@x.io",
        edited_message="Düzenlenmiş mesaj.",
    )
    assert edited["status"] == "edited"
    assert edited["proposed_message"] == "Düzenlenmiş mesaj."


def test_escalation_due_surfaced_for_overdue_pending() -> None:
    """3rd-eye — escalate_at was a dead field (set, never read/exposed). It is
    now in the payload + a computed escalation_due: a pending item past its 4h
    SLA flags overdue; a fresh one doesn't; a decided one never does."""
    from datetime import timedelta

    from sqlmodel import Session

    from app.db.models import ApprovalItem
    from app.db.session import get_engine

    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tEsc", actor="")
    item = service.create_approval_from_result(
        res,
        tenant_slug="tEsc",
        requester="",
        agent_run_id=rid,
    )

    fresh = service.get_approval(tenant_slug="tEsc", item_id=item["id"])
    assert fresh["escalate_at"] is not None  # exposed (was absent)
    assert fresh["escalation_due"] is False  # +4h SLA not yet passed
    assert service.list_approvals(tenant_slug="tEsc")["escalations_due"] == 0

    with Session(get_engine()) as db:  # force the SLA into the past
        row = db.get(ApprovalItem, item["id"])
        row.escalate_at = service._now() - timedelta(hours=1)
        db.add(row)
        db.commit()

    overdue = service.get_approval(tenant_slug="tEsc", item_id=item["id"])
    assert overdue["escalation_due"] is True
    assert service.list_approvals(tenant_slug="tEsc")["escalations_due"] == 1

    service.decide_approval(
        tenant_slug="tEsc",
        item_id=item["id"],
        decision="approve",
        decided_by="b@x.io",
    )
    decided = service.get_approval(tenant_slug="tEsc", item_id=item["id"])
    assert decided["escalation_due"] is False  # decided items never escalate
