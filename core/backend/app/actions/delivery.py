# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Actually sending the message a person approved.

There was no such thing before. `execute_for_approval` wrote a row saying
`status="queued", reason="consent on file · queued to the channel"` and returned,
and nothing in this codebase ever read that row: there is no drainer, no worker,
no `where(status == "queued")` anywhere. The 0026 migration even builds an index
on that column — for a consumer that was never written. So an operator approved an
outbound message, the outbox told them it was on its way, and it sat there
forever.

That is worse than a bug. The product's one promise about outbound comms is
"nothing leaves without you saying so", and the inverse was true: **nothing left at
all, and the panel said it had.**

This module is the missing half. It returns whether the message actually went, and
says why when it did not. Two rules it will not break:

* **A channel with no integration is not a channel.** There is no Twilio, no
  WhatsApp Business, no voice provider in this codebase — those names exist in the
  consent ledger and nowhere else. Reporting an SMS as sent because we wrote a row
  about it is the same lie in a new costume, so they refuse.
* **No SMTP server means no email.** The console fallback that logs the body and
  returns is a development convenience; on a customer's server it would be a
  message that "went out" into a log file. It is not delivery, and it does not
  report itself as delivery.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from app.config import settings

logger = logging.getLogger(__name__)

# The channels a person can approve. Only one of them can currently carry a
# message; the rest are honest about it rather than quietly successful.
DELIVERABLE = {"email"}
KNOWN_CHANNELS = {"email", "sms", "whatsapp", "voice", "phone", "call"}


@dataclass(frozen=True)
class Delivery:
    """What happened. `sent` is the only thing the outbox is allowed to believe."""

    sent: bool
    detail: str


def deliver(*, channel: str, to: str, subject: str, message: str) -> Delivery:
    """Send an approved message, and report honestly on whether it went."""
    channel = (channel or "").strip().lower()

    if channel not in DELIVERABLE:
        # Not "queued". There is nothing to queue it into.
        known = "no integration is configured for this channel"
        if channel not in KNOWN_CHANNELS:
            known = f"'{channel}' is not a channel this server knows how to send on"
        return Delivery(False, f"{known} — nothing was sent")

    if not to:
        return Delivery(False, "no recipient address — nothing was sent")

    if not settings.smtp_host:
        # A self-hosted server with no mail server cannot send mail. Saying so is
        # the entire job here: the alternative is a log line that reads like a
        # delivery receipt.
        logger.warning(
            "approved email not sent: no SMTP server configured (to=%s subject=%r)",
            to,
            subject,
        )
        return Delivery(
            False,
            "no SMTP server is configured (ABS_SMTP_HOST) — nothing was sent",
        )

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(message)
    msg.add_alternative(
        f"<html><body><p>{escape(message).replace(chr(10), '<br>')}</p></body></html>",
        subtype="html",
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001 — a failed send is an outcome, not a crash
        # Not swallowed, not raised: recorded. The outbox row becomes `failed` with
        # this text on it, and a person can retry it. The old sender logged the
        # exception and returned None, so the caller could not tell a delivery from
        # a failure — which is how a message could be marked sent and never leave.
        logger.warning("approved email failed: to=%s err=%s", to, exc)
        return Delivery(False, f"{type(exc).__name__}: {exc}"[:480])

    logger.info("approved email sent: to=%s subject=%r", to, subject)
    return Delivery(True, f"delivered to {to}")
