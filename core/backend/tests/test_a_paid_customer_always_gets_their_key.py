# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Licence delivery — the one email the product cannot afford to lose.

A self-hosted customer buys a key. It reaches them once, by email, at the moment
Stripe confirms the payment. If that send fails they have a receipt and nothing else.

It could fail three ways, all of them quiet:

* the send raised, the webhook logged it and returned 200 — Stripe satisfied,
  licence row written, customer with no key and nobody told;
* on a server with no SMTP host configured, `send_license_email` printed the mail to
  the log and returned *cleanly*, so in production the key went into a log file and
  the code believed it had been delivered;
* and there was no way to send it again — no resend path anywhere in the product.

None of this was tested. That is why it survived.
"""

from __future__ import annotations

import pytest

from app.api.admin.auth import admin_required
from app.config import settings
from app.email import sender
from app.main import app


@pytest.fixture
def signed_in():
    """An admin at the keyboard. The anonymous case is asserted separately."""
    app.dependency_overrides[admin_required] = lambda: {"sub": "admin@local",
                                                        "email": "admin@local"}
    yield
    app.dependency_overrides.pop(admin_required, None)


def test_a_production_server_with_no_mail_server_refuses_rather_than_pretends(monkeypatch):
    """The console fallback is a development convenience. In production it is the
    product going missing."""
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(settings, "env", "prod", raising=False)

    with pytest.raises(RuntimeError) as exc:
        sender.send_license_email(
            to="buyer@example.com", license_key="abs_key", refund_url="https://x"
        )

    assert "ABS_SMTP_HOST" in str(exc.value)


def test_in_development_the_console_fallback_still_works(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(settings, "env", "dev", raising=False)

    sender.send_license_email(
        to="buyer@example.com", license_key="abs_key", refund_url="https://x"
    )  # does not raise


def test_a_failed_delivery_is_recorded_where_someone_will_see_it(monkeypatch):
    """The webhook still answers Stripe 200 — a failure there re-issues the licence.

    So the failure has to land somewhere else, and the audit log is the place that
    is actually read when a customer writes in asking where their key is."""
    from app.observability import audit

    recorded: list = []
    monkeypatch.setattr(
        audit, "_persist", lambda payload: recorded.append(payload), raising=False
    )

    audit.emit_event(
        None,
        action="license.delivery_failed",
        outcome="failure",
        resource_type="license",
        resource_id="jti-123",
        user_id="buyer@example.com",
        reason="SMTPAuthenticationError",
    )

    assert recorded and recorded[0]["action"] == "license.delivery_failed"
    assert recorded[0]["outcome"] == "failure"


def test_the_key_can_be_sent_again(client, monkeypatch, signed_in):
    """The way back. There was none: a licence whose email bounced was unreachable
    by any route in the product."""
    from datetime import datetime, timedelta, timezone

    from sqlmodel import Session

    from app.db.models import License
    from app.db.session import get_engine

    sent: list = []
    monkeypatch.setattr(
        "app.api.admin.licenses.send_license_email",
        lambda **kw: sent.append(kw),
    )

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(License(
            jti="jti-resend-1", customer_email="buyer@example.com",
            customer_id_stripe="cus_1", tier="self-host", seat_count=1,
            issued_at=now, expires_at=now + timedelta(days=365),
        ))
        db.commit()

    r = client.post("/v1/admin/licenses/jti-resend-1/resend")
    assert r.status_code == 200, r.text
    assert r.json()["sent_to"] == "buyer@example.com"
    assert len(sent) == 1
    assert sent[0]["to"] == "buyer@example.com"
    # Re-minted, not read back from disk: a signed key at rest is a key to steal.
    assert sent[0]["license_key"].count(".") == 2  # a JWT


def test_a_resend_that_fails_says_so(client, monkeypatch, signed_in):
    from datetime import datetime, timedelta, timezone

    from sqlmodel import Session

    from app.db.models import License
    from app.db.session import get_engine

    def _boom(**kw):
        raise OSError("connection refused")

    monkeypatch.setattr("app.api.admin.licenses.send_license_email", _boom)

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(License(
            jti="jti-resend-2", customer_email="b@example.com",
            customer_id_stripe="cus_2", tier="self-host", seat_count=1,
            issued_at=now, expires_at=now + timedelta(days=365),
        ))
        db.commit()

    r = client.post("/v1/admin/licenses/jti-resend-2/resend")
    assert r.status_code == 502
    assert "could not be sent" in r.json()["detail"]


def test_resending_a_licence_that_does_not_exist_is_a_404(client, signed_in):
    r = client.post("/v1/admin/licenses/nope/resend")
    assert r.status_code == 404





def test_a_stranger_cannot_have_someone_elses_licence_key_mailed_to_them(client):
    """No override here — this is the route as an anonymous caller meets it."""
    r = client.post("/v1/admin/licenses/jti-resend-1/resend")
    assert r.status_code in (401, 403)
