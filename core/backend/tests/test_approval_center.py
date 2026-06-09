# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Approval Center (DB) — log agent run, open approval, decide; tenant-scoped."""

from __future__ import annotations

import pytest

from app.agents.runtime import AgentResult, Evidence
from app.approvals import service


def _result(agent_id: str = "outbound_draft", risk: str = "high",
            approval: bool = True) -> AgentResult:
    return AgentResult(
        agent_id=agent_id, output_kind="outbound_draft", summary="taslak hazır",
        payload={"message": "Merhaba, teklifimiz ektedir."},
        evidence=[Evidence("rag", "fiyat.pdf", "fiyat aralığı...")],
        confidence=0.8, recommended_action="email gönder", risk=risk,
        requires_approval=approval, provider="cloudflare", elapsed_ms=12,
    )


def test_log_run_create_and_decide() -> None:
    res = _result()
    run_id = service.log_agent_run(res, tenant_slug="tA", actor="a@x.io", task="taslak yaz")
    assert isinstance(run_id, int) and run_id > 0

    item = service.create_approval_from_result(
        res, tenant_slug="tA", requester="a@x.io", agent_run_id=run_id,
        target_company="Kaya İnşaat", channel="email", consent_status="opt-in",
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
        tenant_slug="tA", item_id=item["id"], decision="approve",
        decided_by="boss@x.io", note="ok",
    )
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "boss@x.io"
    assert decided["outcome"] == "ok"


def test_approval_tenant_isolation() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tX", actor="")
    item = service.create_approval_from_result(res, tenant_slug="tX", requester="", agent_run_id=rid)
    # other tenant cannot read or decide it (application-layer scope)
    assert service.get_approval(tenant_slug="tY", item_id=item["id"]) is None
    assert service.decide_approval(
        tenant_slug="tY", item_id=item["id"], decision="approve", decided_by="x"
    ) is None


def test_invalid_decision_raises() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tZ", actor="")
    item = service.create_approval_from_result(res, tenant_slug="tZ", requester="", agent_run_id=rid)
    with pytest.raises(ValueError):
        service.decide_approval(
            tenant_slug="tZ", item_id=item["id"], decision="bogus", decided_by="x"
        )


def test_recent_agent_runs_tenant_scoped() -> None:
    service.log_agent_run(
        _result(agent_id="knowledge_base", risk="low", approval=False),
        tenant_slug="tR", actor="a@x.io", task="soru",
    )
    runs = service.recent_agent_runs(tenant_slug="tR", limit=10)
    assert len(runs) >= 1
    assert runs[0]["agent_id"] == "knowledge_base"  # newest first
    # isolation: a fresh tenant sees none of tR's runs
    assert service.recent_agent_runs(tenant_slug="tR-empty-xyz") == []


def test_edit_updates_message() -> None:
    res = _result()
    rid = service.log_agent_run(res, tenant_slug="tE", actor="")
    item = service.create_approval_from_result(res, tenant_slug="tE", requester="", agent_run_id=rid)
    edited = service.decide_approval(
        tenant_slug="tE", item_id=item["id"], decision="edit",
        decided_by="ed@x.io", edited_message="Düzenlenmiş mesaj.",
    )
    assert edited["status"] == "edited"
    assert edited["proposed_message"] == "Düzenlenmiş mesaj."
