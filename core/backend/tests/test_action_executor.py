# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stage E — approval → action executor (consent-gated, and it actually sends).

The old version of this file asserted `status == "queued"` and called it a pass.
Nothing drained that queue; the message never went. The tests were green the whole
time, which is the point: an outbox status is not evidence of anything unless
something checks that a message left the building.

So these tests check delivery, not vocabulary.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session

from app.actions import (
    RetryNotAllowed,
    execute_for_approval,
    list_actions,
    retry_action,
)
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


class _FakeSMTP:
    """A mail server that records what it was handed."""

    sent: list = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=10):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if _FakeSMTP.fail_with:
            raise _FakeSMTP.fail_with
        _FakeSMTP.sent.append(msg)


@pytest.fixture
def mail(monkeypatch):
    """A configured SMTP server that works — the state a customer's server is in."""
    from app.config import settings

    _FakeSMTP.sent = []
    _FakeSMTP.fail_with = None
    monkeypatch.setattr(settings, "smtp_host", "mail.test", raising=False)
    monkeypatch.setattr(settings, "smtp_user", "", raising=False)
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    return _FakeSMTP


def _company_with_contact(tenant: str, name: str, email: str) -> None:
    with Session(get_engine()) as db:
        c = Company(tenant_slug=tenant, name=name)
        db.add(c)
        db.commit()
        db.refresh(c)
        db.add(
            Contact(tenant_slug=tenant, company_id=c.id, name="Yetkili", email=email)
        )
        db.commit()


def _consented(tenant: str, company: str, email: str) -> None:
    _company_with_contact(tenant, company, email)
    set_consent(
        tenant_slug=tenant,
        contact_email=email,
        email_consent=True,
        legal_basis="consent",
    )


# ── the message actually goes ────────────────────────────────────────────────
def test_an_approved_email_actually_reaches_the_mail_server(mail):
    t = "t_act_ok"
    _consented(t, "İzinli A.Ş.", "yetkili@izinli.com")

    out = execute_for_approval(
        _Item(
            channel="email",
            target_company="İzinli A.Ş.",
            id=10,
            proposed_message="Merhaba, teklifimiz ektedir.",
        ),
        tenant_slug=t,
    )

    assert out["status"] == "sent"
    assert out["action_kind"] == "message_send"
    assert out["target_contact"] == "yetkili@izinli.com"
    # The row says sent because a message was handed to a mail server — not
    # because a row was written about one.
    assert len(mail.sent) == 1
    assert mail.sent[0]["To"] == "yetkili@izinli.com"
    assert "teklifimiz" in mail.sent[0].get_body(("plain",)).get_content()


def test_nothing_is_sent_and_nothing_claims_to_be_when_there_is_no_mail_server(
    monkeypatch,
):
    """A self-hosted server with no SMTP host cannot send. It says so."""
    from app.config import settings

    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    t = "t_act_nosmtp"
    _consented(t, "Postasız A.Ş.", "y@postasiz.com")

    out = execute_for_approval(
        _Item(channel="email", target_company="Postasız A.Ş."), tenant_slug=t
    )

    assert out["status"] == "failed"
    assert "no SMTP server" in out["reason"]


def test_a_channel_with_no_integration_refuses_instead_of_claiming_delivery(mail):
    """There is no Twilio, no WhatsApp Business, no voice provider in this codebase.

    Consent for a channel we cannot send on is still not a send."""
    t = "t_act_nochannel"
    _company_with_contact(t, "WhatsApp Ltd", "w@wa.com")
    set_consent(
        tenant_slug=t,
        contact_email="w@wa.com",
        email_consent=True,
        whatsapp_consent=True,
        legal_basis="consent",
    )

    out = execute_for_approval(
        _Item(channel="whatsapp", target_company="WhatsApp Ltd"), tenant_slug=t
    )

    assert out["status"] == "failed"
    assert "nothing was sent" in out["reason"]
    assert mail.sent == []


def test_an_smtp_failure_is_recorded_not_swallowed(mail):
    t = "t_act_smtperr"
    _consented(t, "Hatalı A.Ş.", "h@hatali.com")
    mail.fail_with = OSError("connection refused")

    out = execute_for_approval(
        _Item(channel="email", target_company="Hatalı A.Ş."), tenant_slug=t
    )

    assert out["status"] == "failed"
    assert "connection refused" in out["reason"]


# ── internal actions ─────────────────────────────────────────────────────────
def test_an_internal_action_with_no_handler_says_so_instead_of_executed():
    """It used to write `executed · internal action applied` and change nothing.

    There is no CRM-note handler, no merge handler, no field-update handler. An
    operator approving one of those got a green row over an unchanged database."""
    out = execute_for_approval(
        _Item(channel="crm_note", agent_id="crm_hygiene"), tenant_slug="t_act_int"
    )

    assert out["status"] == "failed"
    assert out["action_kind"] == "internal"
    assert "no handler" in out["reason"]


# ── consent gate (fail-closed) ───────────────────────────────────────────────
def test_outbound_blocked_when_no_consent_record(mail):
    t = "t_act_noconsent"
    _company_with_contact(t, "Kayıtsız Ltd", "x@kayitsiz.com")
    out = execute_for_approval(
        _Item(channel="email", target_company="Kayıtsız Ltd"), tenant_slug=t
    )
    assert out["status"] == "blocked"  # fail-closed
    assert mail.sent == []


def test_outbound_blocked_for_unconsented_channel(mail):
    t = "t_act_partial"
    _company_with_contact(t, "Kısmi A.Ş.", "k@kismi.com")
    # email only — phone/whatsapp not consented
    set_consent(tenant_slug=t, contact_email="k@kismi.com", email_consent=True)
    email = execute_for_approval(
        _Item(channel="email", target_company="Kısmi A.Ş."), tenant_slug=t
    )
    wa = execute_for_approval(
        _Item(channel="whatsapp", target_company="Kısmi A.Ş."), tenant_slug=t
    )
    assert email["status"] == "sent"
    assert wa["status"] == "blocked"
    assert len(mail.sent) == 1


def test_outbound_blocked_when_recipient_unresolved():
    out = execute_for_approval(
        _Item(channel="email", target_company="Yok Şirketi"),
        tenant_slug="t_act_unresolved",
    )
    assert out["status"] == "blocked"
    assert "could not be resolved" in out["reason"]


# ── retry ────────────────────────────────────────────────────────────────────
def test_a_failed_message_can_be_sent_again_when_the_mail_server_comes_back(mail):
    t = "t_act_retry"
    _consented(t, "Geçici A.Ş.", "g@gecici.com")
    mail.fail_with = OSError("connection refused")
    failed = execute_for_approval(
        _Item(
            channel="email",
            target_company="Geçici A.Ş.",
            proposed_message="tekrar denenecek",
        ),
        tenant_slug=t,
    )
    assert failed["status"] == "failed"

    mail.fail_with = None
    out = retry_action(tenant_slug=t, action_id=failed["id"])

    assert out["status"] == "sent"
    assert len(mail.sent) == 1
    # the same row, not a second one
    assert list_actions(tenant_slug=t)["total"] == 1


def test_a_sent_message_is_not_sent_twice(mail):
    t = "t_act_retry_sent"
    _consented(t, "Gitti A.Ş.", "g@gitti.com")
    row = execute_for_approval(
        _Item(channel="email", target_company="Gitti A.Ş."), tenant_slug=t
    )
    assert row["status"] == "sent"

    with pytest.raises(RetryNotAllowed):
        retry_action(tenant_slug=t, action_id=row["id"])
    assert len(mail.sent) == 1


def test_retry_re_checks_consent_and_blocks_if_it_was_withdrawn(mail):
    t = "t_act_retry_optout"
    _consented(t, "Vazgeçen A.Ş.", "v@vazgecen.com")
    mail.fail_with = OSError("down")
    failed = execute_for_approval(
        _Item(channel="email", target_company="Vazgeçen A.Ş."), tenant_slug=t
    )
    assert failed["status"] == "failed"

    set_consent(tenant_slug=t, contact_email="v@vazgecen.com", email_consent=False)
    mail.fail_with = None
    out = retry_action(tenant_slug=t, action_id=failed["id"])

    assert out["status"] == "blocked"
    assert mail.sent == []


def test_retry_is_tenant_scoped(mail):
    t = "t_act_retry_tenant"
    _consented(t, "Sahip A.Ş.", "s@sahip.com")
    mail.fail_with = OSError("down")
    failed = execute_for_approval(
        _Item(channel="email", target_company="Sahip A.Ş."), tenant_slug=t
    )

    with pytest.raises(KeyError):
        retry_action(tenant_slug="t_act_retry_intruder", action_id=failed["id"])


# ── idempotency: re-deciding must not re-fire the action ─────────────────────
def test_decide_fires_action_at_most_once(mail):
    from app.approvals import decide_approval
    from app.db.models import ApprovalItem

    t = "t_act_idem"
    _consented(t, "Tekrar A.Ş.", "y@tekrar.com")
    with Session(get_engine()) as db:
        ap = ApprovalItem(
            tenant_slug=t,
            agent_id="outbound_draft",
            action="email gönder",
            target_company="Tekrar A.Ş.",
            channel="email",
            status="pending",
        )
        db.add(ap)
        db.commit()
        db.refresh(ap)
        ap_id = ap.id

    from app.approvals.service import AlreadyDecided

    d1 = decide_approval(
        tenant_slug=t, item_id=ap_id, decision="approve", decided_by="u"
    )
    assert d1["action"] is not None  # first decision fires

    # The second decision is refused outright now, rather than quietly rewriting
    # the row and returning 200 with no action attached. Nothing re-fired before
    # either — but the record could be left saying "approved" over a decision
    # somebody had made the other way, which is a lie the outbox cannot see.
    with pytest.raises(AlreadyDecided):
        decide_approval(
            tenant_slug=t, item_id=ap_id, decision="approve", decided_by="u"
        )

    assert list_actions(tenant_slug=t)["total"] == 1
    assert len(mail.sent) == 1  # one approval, one message


# ── outbox listing ───────────────────────────────────────────────────────────
def test_list_actions_tallies_by_status(mail):
    t = "t_act_list"
    execute_for_approval(
        _Item(channel="crm_note", agent_id="crm_hygiene"), tenant_slug=t
    )
    execute_for_approval(_Item(channel="email", target_company="Yok"), tenant_slug=t)
    out = list_actions(tenant_slug=t)
    assert out["total"] == 2
    assert out["by_status"].get("failed") == 1  # internal, no handler
    assert out["by_status"].get("blocked") == 1  # email, no recipient
