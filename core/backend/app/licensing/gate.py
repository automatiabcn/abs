# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Is this install licensed? Answered without touching the network.

The licence key is an RS256 JWT that we signed. Everything worth checking about
it — the signature, the expiry, the machine binding — can be checked against a
public key on the customer's own disk. That is the gate, and it is offline.

What we *cannot* know offline is that a licence was **revoked** after it was
issued: a refund, a chargeback, a cancelled contract. That is what the
activation server is for. So the two questions are separated:

    signature  → decided locally, in the request path, always available
    revocation → decided by the server, out of band, cached on disk

and the cache is only ever written from a real server response
(``phone_home._persist_activation_state``). An offline-grace verdict is never
persisted. So a cached ``valid: false`` means *the server said no*; a missing
cache means *we have not managed to ask*. Those are different facts, and the
old chat gate collapsed them into one 403.

It refused a request when it could not reach us. On a fresh install that is
every request — the customer's product was dead in its first minute because
*our* server had not been spoken to yet. Worse, it did the asking synchronously,
inside `POST /v1/chat/completions`, so our activation host sat in the request
path of every chat turn on every customer's machine.

The rule now:

    a bad signature refuses          — that is the licence being wrong
    a server revocation refuses      — that is the licence being cancelled
    a network failure never refuses  — that is *our* problem, not the customer's
    no licence key at all is a TRIAL — seven days, and then chat stops

The product is a monthly subscription. There is no free tier: a server that keeps
answering questions forever without one is not a trial, it is the product, given
away. What the trial's end does *not* touch is the customer's own data — their
documents, transcripts and keys stay readable, exportable and deletable, because
holding a person's data hostage to a renewal is not a business model.

And the network rule survives all of it. A customer who has paid, on a machine
that cannot reach us, keeps working: the signature on their key is checkable on
their own disk, and an outage of ours is not a reason to break their product.
"""

from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# Past `exp`, the licence keeps working for this long. Renewals land late,
# invoices sit in an inbox for a week, and a customer mid-sentence in a chat
# window is not the person to punish for it. Matches `verifier.GRACE_DAYS`.
GRACE_DAYS = 7
_GRACE_SECONDS = GRACE_DAYS * 86400


class Verdict(str, enum.Enum):
    LICENSED = "licensed"
    TRIAL = "trial"  # no key yet, inside the seven days
    TRIAL_EXPIRED = "trial_expired"  # no key, and the seven days are up
    UNLICENSED = "unlicensed"  # no key configured (kept: some callers still read it)
    IN_GRACE = "in_grace"  # expired, still inside the grace window
    EXPIRED = "expired"  # expired, past the grace window
    INVALID = "invalid"  # bad signature, malformed, wrong machine
    REVOKED = "revoked"  # the activation server said no


@dataclass(frozen=True)
class Decision:
    allowed: bool
    verdict: Verdict
    reason: str = ""

    @property
    def detail(self) -> str:
        """What the customer is told when they are refused.

        A person who has just watched their trial end is not debugging our
        enum — they want to know what happened and what to do. The machine-
        readable part stays first (the panel keys off it); the sentence follows.
        """
        if self.verdict is Verdict.REVOKED:
            return f"license_revoked:{self.reason or 'revoked'}"
        if self.verdict is Verdict.EXPIRED:
            return (
                "license_expired: your subscription has lapsed. Chat and the agent "
                "are paused — your documents, meetings and keys are still here and "
                "still yours to export or delete. Renew in the panel under Settings "
                "→ Licence."
            )
        if self.verdict is Verdict.TRIAL_EXPIRED:
            return (
                "trial_expired: the seven-day trial is over. Chat and the agent are "
                "paused — nothing you put on this server has been touched, and you "
                "can still read, export or delete all of it. Subscribe in the panel "
                "under Settings → Licence."
            )
        return "license_invalid"


def _bypassed() -> Optional[str]:
    """The escape hatches, named so a reader can see exactly how wide they are.

    `ABS_TEST_MODE` is the reason this gate went untested for its whole life:
    conftest sets it session-wide, so ~2900 tests exercise an unlicensed
    application. It stays (the suite needs it) but the licence tests delete it
    and drive the real thing.
    """
    if os.environ.get("ABS_TEST_MODE") == "1":
        return "test_mode"
    if os.environ.get("ABS_LICENSE_GATE_DISABLED") == "1":
        return "gate_disabled"
    return None


def _demo_active() -> bool:
    try:
        from app.licensing.demo import is_active

        return bool(is_active())
    except Exception:  # pragma: no cover — demo module optional
        return False


def _revoked_in_db(jti: Optional[str]) -> Optional[str]:
    """The refund flow. An admin revokes a licence and `License.revoked_at` is
    set — this is what actually happens on a chargeback, and it is what
    `/v1/license/info` has always reported.

    The chat gate did not read it. It watched the activation cache instead, so
    a licence revoked here kept answering chat requests. Two revocation
    sources, one of them unwatched.

    A DB failure is swallowed: a cryptographically valid licence must not be
    refused because a lookup broke.
    """
    if not jti:
        return None
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            row = db.scalars(select(License).where(License.jti == jti)).first()
    except Exception as exc:  # pragma: no cover — DB not ready
        logger.debug("license_revocation_db_lookup_skip: %s", exc)
        return None

    if row is None or row.revoked_at is None:
        return None
    return str(row.revoked_reason or "revoked")


def _revoked_by_server() -> Optional[str]:
    """The reason the activation server refused, or None.

    Only a persisted server response can produce a refusal here. A missing
    cache (never activated, no network, our host down) returns None — not a
    refusal. That asymmetry is the whole point of this module.
    """
    try:
        from app.licensing.phone_home import get_cached_license_state

        state: dict[str, Any] = get_cached_license_state() or {}
    except Exception as exc:  # pragma: no cover — unreadable state file
        logger.warning("license_state_unreadable: %s", exc)
        return None

    if not state or state.get("valid", True):
        return None

    reason = str(state.get("reason") or "revoked")
    # These are written by *us*, locally, when the server could not be reached.
    # They are not verdicts and must never refuse a request. They cannot reach
    # the cache today (offline-grace results are not persisted), but a future
    # edit to phone_home could start persisting them, and the failure mode
    # would be every customer locked out of a product they paid for.
    if reason.startswith("offline_grace") or reason == "never_activated":
        logger.debug("license_state_offline_marker reason=%s (ignored)", reason)
        return None
    return reason


def _revoked(payload: Optional[dict]) -> Optional[str]:
    """Either revocation source. Both are real; both must bite."""
    jti = (payload or {}).get("jti")
    return _revoked_in_db(jti) or _revoked_by_server()


def enforce() -> Decision:
    """What the request path acts on: `evaluate()`, plus the escape hatches.

    The hatches belong here and nowhere else. When they lived inside
    `evaluate()`, `/v1/license/info` — which only *describes* the licence —
    inherited them, and a dev box with the gate switched off reported a garbage
    key as "licensed". A surface whose job is to tell the operator the truth
    must not be reading through a bypass.
    """
    bypass = _bypassed()
    if bypass:
        return Decision(True, Verdict.LICENSED, bypass)
    return evaluate()


def evaluate() -> Decision:
    """Where this install actually stands. Never blocks, never opens a socket,
    and never lies because someone set an environment variable."""
    token = (settings.license_key or "").strip()
    if not token:
        # No key means the trial — seven days from the moment this server was
        # installed, then chat and the agent stop. It is not a free tier any more:
        # the product is a monthly subscription, and a server that answers
        # questions forever without one is not a trial, it is the product.
        #
        # What does *not* stop is access to what the customer put here. Their
        # documents, transcripts and keys stay readable, exportable and
        # deletable. Holding a person's own data hostage to a renewal is not a
        # business model, it is a hostage situation.
        #
        # There is exactly one free window, and this is it. The fourteen-day
        # "demo" used to be a second one, armed on the same empty key and
        # answering to a different clock — two implementations of one rule, which
        # is how a customer ends up served by their editor and refused by their
        # panel. `licensing.demo` now reads this trial; it is a name, not a
        # timer.
        from app.licensing import trial

        state = trial.status()
        if state.active:
            return Decision(True, Verdict.TRIAL, f"trial_days_left:{state.days_left}")
        return Decision(False, Verdict.TRIAL_EXPIRED, "trial_elapsed")

    from app.licensing.verifier import verify_license

    try:
        payload = verify_license(token)
    except jwt.ExpiredSignatureError:
        return _grace(token)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        # `verify_license` turns an expired token into an HTTP 401 before we
        # ever see PyJWT's exception, so the grace window is checked here too.
        if detail == "License has expired":
            return _grace(token)
        reason = str(detail or type(exc).__name__)
        logger.warning("license_invalid reason=%s", reason)
        return Decision(False, Verdict.INVALID, reason)

    revoked = _revoked(payload)
    if revoked:
        logger.warning("license_revoked reason=%s", revoked)
        return Decision(False, Verdict.REVOKED, revoked)

    return Decision(True, Verdict.LICENSED, "")


def _grace(token: str) -> Decision:
    """An expired licence, re-checked with the grace window allowed for."""
    from app.licensing.keys import load_public_key

    try:
        payload = jwt.decode(
            token,
            key=load_public_key(settings.public_key_path),
            algorithms=["RS256"],
            leeway=_GRACE_SECONDS,
            options={"require": ["exp", "iat", "jti"]},
        )
    except Exception:
        logger.warning("license_expired_past_grace grace_days=%d", GRACE_DAYS)
        return Decision(False, Verdict.EXPIRED, "grace_elapsed")

    # Still expired — but inside the window, and a revocation still bites.
    revoked = _revoked(payload)
    if revoked:
        return Decision(False, Verdict.REVOKED, revoked)

    logger.info("license_in_grace grace_days=%d", GRACE_DAYS)
    return Decision(True, Verdict.IN_GRACE, "grace")
