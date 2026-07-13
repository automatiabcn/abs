# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stage E — approval → action executor (consent-gated outbox)."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from app.actions import execute_for_approval, list_actions
from app.consent.service import set_consent
from app.db.growth_models import Company, Contact
from app.db.session import get_engine


class _Item:
    """Minimal ApprovalItem stand-in (executor only reads attributes)."""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.agent_id = kw.get("agent_id", "outbound_draft")
        self.channel = kw.get("channel", "")
        self.target_company = kw.get("target_company", "")
        self.proposed_message = kw.get("proposed_message", "")
        self.action = kw.get("action", "do the thing")


def _company_with_contact(tenant: str, name: str, email: str) -> None:
    with Session(get_engine()) as db:
        c = Company(tenant_slug=tenant, name=name)
        db.add(c)
        db.commit()
        db.refresh(c)
        db.add(Contact(tenant_slug=tenant, company_id=c.id, name="Yetkili", email=email))
        db.commit()


# ── internal actions (no channel) ────────────────────────────────────────────
def test_internal_action_executes_immediately():
    out = execute_for_approval(_Item(channel="", agent_id="crm_hygiene"), tenant_slug="t_act_int")
    assert out["status"] == "executed"
    assert out["action_kind"] == "internal"


# ── outbound: consent gate ───────────────────────────────────────────────────
def test_outbound_queued_when_consent_granted():
    t = "t_act_ok"
    _company_with_contact(t, "İzinli A.Ş.", "yetkili@izinli.com")
    set_consent(tenant_slug=t, contact_email="yetkili@izinli.com",
                email_consent=True, legal_basis="consent")
    out = execute_for_approval(
        _Item(channel="email", target_company="İzinli A.Ş.", id=10), tenant_slug=t)
    assert out["status"] == "queued"
    assert out["action_kind"] == "message_send"
    assert out["target_contact"] == "yetkili@izinli.com"


def test_outbound_blocked_when_no_consent_record():
    t = "t_act_noconsent"
    _company_with_contact(t, "Kayıtsız Ltd", "x@kayitsiz.com")
    out = execute_for_approval(
        _Item(channel="whatsapp", target_company="Kayıtsız Ltd"), tenant_slug=t)
    assert out["status"] == "blocked"  # fail-closed


def test_outbound_blocked_for_unconsented_channel():
    t = "t_act_partial"
    _company_with_contact(t, "Kısmi A.Ş.", "k@kismi.com")
    # email only — phone/whatsapp not consented
    set_consent(tenant_slug=t, contact_email="k@kismi.com", email_consent=True)
    email = execute_for_approval(_Item(channel="email", target_company="Kısmi A.Ş."), tenant_slug=t)
    wa = execute_for_approval(_Item(channel="whatsapp", target_company="Kısmi A.Ş."), tenant_slug=t)
    assert email["status"] == "queued"
    assert wa["status"] == "blocked"


def test_outbound_blocked_when_recipient_unresolved():
    out = execute_for_approval(
        _Item(channel="email", target_company="Yok Şirketi"), tenant_slug="t_act_unresolved")
    assert out["status"] == "blocked"
    assert "could not be resolved" in out["reason"]


# ── idempotency: re-deciding must not re-fire the action ─────────────────────
def test_decide_fires_action_at_most_once():
    from app.approvals import decide_approval
    from app.db.models import ApprovalItem

    t = "t_act_idem"
    _company_with_contact(t, "Tekrar A.Ş.", "y@tekrar.com")
    set_consent(tenant_slug=t, contact_email="y@tekrar.com", email_consent=True)
    with Session(get_engine()) as db:
        ap = ApprovalItem(tenant_slug=t, agent_id="outbound_draft", action="email gönder",
                          target_company="Tekrar A.Ş.", channel="email", status="pending")
        db.add(ap)
        db.commit()
        db.refresh(ap)
        ap_id = ap.id

    from app.approvals.service import AlreadyDecided

    d1 = decide_approval(tenant_slug=t, item_id=ap_id, decision="approve", decided_by="u")
    assert d1["action"] is not None        # first decision fires

    # The second decision is refused outright now, rather than quietly rewriting
    # the row and returning 200 with no action attached. Nothing re-fired before
    # either — but the record could be left saying "approved" over a decision
    # somebody had made the other way, which is a lie the outbox cannot see.
    with pytest.raises(AlreadyDecided):
        decide_approval(tenant_slug=t, item_id=ap_id, decision="approve", decided_by="u")

    assert list_actions(tenant_slug=t)["total"] == 1


# ── outbox listing ───────────────────────────────────────────────────────────
def test_list_actions_tallies_by_status():
    t = "t_act_list"
    execute_for_approval(_Item(channel="", agent_id="crm_hygiene"), tenant_slug=t)
    execute_for_approval(_Item(channel="email", target_company="Yok"), tenant_slug=t)
    out = list_actions(tenant_slug=t)
    assert out["total"] == 2
    assert out["by_status"].get("executed") == 1
    assert out["by_status"].get("blocked") == 1
