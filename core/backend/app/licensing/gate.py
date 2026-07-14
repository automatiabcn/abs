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
    no licence key at all is allowed — that is the free tier, and it must work

Commercial use without a licence is prevented by the Business Source Licence and
a contract, not by breaking the software of the people who paid us.
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
    UNLICENSED = "unlicensed"  # no key configured — the free tier
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
        """The `detail` an HTTP 403 carries. Stable — the panel reads it."""
        if self.verdict is Verdict.REVOKED:
            return f"license_revoked:{self.reason or 'revoked'}"
        if self.verdict is Verdict.EXPIRED:
            return "license_expired"
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
        # The free tier. It has to be excellent, and it cannot be excellent
        # while 403ing. Checked *before* demo mode, which auto-arms on an empty
        # key: both are allowed, but "no licence" and "showcase install" are
        # different facts and the settings page reports them differently.
        return Decision(True, Verdict.UNLICENSED, "no_license_key")

    if _demo_active():
        return Decision(True, Verdict.LICENSED, "demo")

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
