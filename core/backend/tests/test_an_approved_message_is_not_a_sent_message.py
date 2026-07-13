# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The delivery path itself — `app.actions.delivery`.

The product makes exactly one promise about outbound comms: *nothing leaves
without you saying so.* The inverse turned out to be true — **nothing left at
all, and the panel said it had.** `execute_for_approval` wrote `status="queued"`
and returned, and there is no drainer, no worker, no `where(status == "queued")`
anywhere in this codebase.

These tests pin down the rule that replaced it: a status of `sent` may only be
written when a message was actually handed to a mail server. Everything else says
what stopped it.
"""

from __future__ import annotations

import pytest

from app.actions import delivery


class _FakeSMTP:
    sent: list = []
    fail_with: Exception | None = None
    tls: int = 0
    logins: list = []

    def __init__(self, host, port, timeout=10):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        _FakeSMTP.tls += 1

    def login(self, user, password):
        _FakeSMTP.logins.append(user)

    def send_message(self, msg):
        if _FakeSMTP.fail_with:
            raise _FakeSMTP.fail_with
        _FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    from app.config import settings

    _FakeSMTP.sent, _FakeSMTP.fail_with, _FakeSMTP.tls, _FakeSMTP.logins = (
        [],
        None,
        0,
        [],
    )
    monkeypatch.setattr(settings, "smtp_host", "mail.test", raising=False)
    monkeypatch.setattr(settings, "smtp_port", 587, raising=False)
    monkeypatch.setattr(settings, "smtp_user", "postmaster", raising=False)
    monkeypatch.setattr(settings, "smtp_password", "s3cret", raising=False)
    monkeypatch.setattr(settings, "smtp_from", "abs@test", raising=False)
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    return _FakeSMTP


def test_an_email_is_delivered_over_tls_and_reported_as_sent(smtp):
    out = delivery.deliver(channel="email", to="a@b.com", subject="Hi", message="Body")

    assert out.sent is True
    assert "a@b.com" in out.detail
    assert len(smtp.sent) == 1
    assert smtp.tls == 1  # never in the clear
    assert smtp.logins == ["postmaster"]
    assert smtp.sent[0]["Subject"] == "Hi"


def test_the_body_is_escaped_in_the_html_part(smtp):
    """A drafted message is model output. It does not get to inject markup."""
    delivery.deliver(
        channel="email",
        to="a@b.com",
        subject="Hi",
        message="<script>alert(1)</script> & co",
    )

    html = smtp.sent[0].get_body(("html",)).get_content()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


@pytest.mark.parametrize("channel", ["whatsapp", "sms", "voice", "phone", "call"])
def test_a_channel_with_no_integration_never_reports_a_send(smtp, channel):
    """There is no Twilio, no WhatsApp Business, no voice provider in this repo.

    Those names live in the consent ledger and nowhere else. Writing a row about
    an SMS is not sending an SMS."""
    out = delivery.deliver(channel=channel, to="a@b.com", subject="Hi", message="Body")

    assert out.sent is False
    assert "nothing was sent" in out.detail
    assert smtp.sent == []


def test_an_unknown_channel_says_it_is_unknown(smtp):
    out = delivery.deliver(
        channel="carrier_pigeon", to="a@b.com", subject="Hi", message="B"
    )
    assert out.sent is False
    assert "carrier_pigeon" in out.detail


def test_no_mail_server_is_a_failure_not_a_console_log(monkeypatch):
    """Dev convenience — log the body and return — is a message that 'went out'
    into a log file. On a customer's server that is not delivery."""
    from app.config import settings

    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    out = delivery.deliver(channel="email", to="a@b.com", subject="Hi", message="B")

    assert out.sent is False
    assert "ABS_SMTP_HOST" in out.detail


def test_no_recipient_is_a_failure(smtp):
    out = delivery.deliver(channel="email", to="", subject="Hi", message="B")
    assert out.sent is False
    assert smtp.sent == []


def test_an_smtp_error_is_returned_not_raised_and_not_swallowed(smtp):
    """The old sender logged the exception and returned None, so the caller could
    not tell a delivery from a failure. That is how a message gets marked sent and
    never leaves."""
    smtp.fail_with = TimeoutError("timed out")

    out = delivery.deliver(channel="email", to="a@b.com", subject="Hi", message="B")

    assert out.sent is False
    assert "TimeoutError" in out.detail and "timed out" in out.detail


def test_the_detail_fits_the_column_it_is_stored_in(smtp):
    """`ActionExecution.reason` is 256 chars. A 10 KB SMTP rejection must not blow
    up the write that records the failure."""
    smtp.fail_with = RuntimeError("x" * 10_000)

    out = delivery.deliver(channel="email", to="a@b.com", subject="Hi", message="B")

    assert out.sent is False
    assert len(out.detail) <= 512
