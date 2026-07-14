# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""How a monthly subscription stays alive on a server we cannot see.

The licence is a signed token with an expiry, checked offline. That is what makes
the product work on a machine with no internet and no permission to phone anyone
— and it is also the problem, because a token that is valid for a year does not
notice that the customer stopped paying in month two. Enforcing a monthly
subscription with an annual key means enforcing it with a lawyer.

So the key is short. It is minted to last until the end of the billing period the
customer has actually paid for, plus the grace window, and this module is how the
customer's server gets the next one: a few days before the key runs out it asks
for a fresh one, and the seller mints it only if the subscription is still alive
in Stripe. Stop paying, and the key on the server simply runs out — offline,
air-gapped, whatever. Nobody has to be locked out by a remote switch, because
nothing has to be switched off.

Two rules hold this together:

**Renewal never blocks.** It happens in the background, on a schedule, never in a
request path. If the renewal service is unreachable — our outage, their firewall,
a flight — nothing is refused. There are days of key left, and then the grace
window on top of that. A customer must never watch their own server stop because
*we* could not be reached.

**A new key is only installed if it is better.** It has to carry a real signature,
it has to belong to the same customer, and it has to outlive the key already
installed. Anything else is not a renewal — it is someone handing this server a
different licence, and the answer to that is no.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Start asking this many days before the key runs out. The grace window (7 days)
# sits behind this, so a renewal service that is down for a long weekend costs
# the customer nothing at all.
RENEW_BEFORE_DAYS = 3

_TIMEOUT_S = 8.0

# The last thing renewal did, so the panel can say it out loud.
#
# A renewal that quietly fails is the worst failure this module has, because it
# looks exactly like one that quietly works — right up to the morning the key runs
# out and a paying customer's server stops for a reason nobody warned them about.
# So every attempt is recorded, and `/v1/license/info` reports it.
_LAST: Dict[str, Any] = {"attempted_at": None, "ok": None, "error": None}


def last_attempt() -> Dict[str, Any]:
    return dict(_LAST)


def _record(ok: bool, error: Optional[str] = None) -> None:
    import time

    _LAST.update({"attempted_at": time.time(), "ok": ok, "error": error})


def _claims(token: str) -> Dict[str, Any]:
    """The token's own claims, signature unchecked and expiry ignored.

    Only ever used to answer "when does this run out" — never to decide anything.
    A decision goes through `verify_license`.
    """
    import jwt as pyjwt

    try:
        return dict(
            pyjwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
        )
    except Exception:  # noqa: BLE001 — an unreadable key is not a renewable one
        return {}


def seconds_left(token: str) -> Optional[float]:
    import time

    exp = _claims(token).get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return float(exp) - time.time()


def is_due(token: str) -> bool:
    """Is it time to ask for the next key?"""
    left = seconds_left(token)
    if left is None:
        return False
    return left <= RENEW_BEFORE_DAYS * 86400


def apply_renewed_key(token: str) -> bool:
    """Install a freshly minted key, if it is genuinely a better one.

    Returns True when the key on this server was replaced.
    """
    from app.licensing.verifier import verify_license

    candidate = (token or "").strip()
    if not candidate:
        return False

    try:
        payload = verify_license(candidate)
    except Exception as exc:  # noqa: BLE001
        logger.warning("renewal_rejected reason=bad_signature err=%s", exc)
        return False

    current = (settings.license_key or "").strip()
    if current:
        mine = _claims(current)
        # The same customer, or it is not a renewal. A renewal endpoint that can
        # hand this server somebody else's licence is a licence swap, not a
        # renewal.
        if mine.get("customer_id") and payload.get("customer_id") != mine.get(
            "customer_id"
        ):
            logger.warning("renewal_rejected reason=different_customer")
            return False
        # And it has to last longer than what is already here — otherwise a
        # replayed old key is a downgrade someone else gets to choose.
        if float(payload.get("exp", 0)) <= float(mine.get("exp", 0) or 0):
            logger.info("renewal_skipped reason=not_newer")
            return False

    settings.license_key = candidate
    try:
        from app.api.setup import _persist_encrypted_secret

        _persist_encrypted_secret("license_key", candidate)
    except Exception as exc:  # noqa: BLE001 — in-process key still took effect
        logger.error(
            "renewal_not_persisted err=%s — the new key works until this process "
            "restarts, and then the old one comes back",
            exc,
        )
        return True

    logger.info("license_renewed jti=%s exp=%s", payload.get("jti"), payload.get("exp"))
    return True


async def renew_if_due(token: Optional[str] = None) -> bool:
    """Ask for the next key when the current one is nearly out. Never raises."""
    current = (token or settings.license_key or "").strip()
    if not current:
        return False  # a trial has nothing to renew
    if not settings.license_renewal_url:
        return False
    if not is_due(current):
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            res = await client.post(
                settings.license_renewal_url,
                json={"license_key": current},
            )
    except Exception as exc:  # noqa: BLE001 — our outage is not their problem
        # Nothing is refused. But a customer who is paying us and whose key is
        # days from running out has to hear about it while there is still time to
        # do something, so this is loud and it reaches the licence page.
        logger.error(
            "renewal_unreachable url=%s err=%s — the licence on this server expires "
            "in %.1f days and could not be renewed. Nothing is blocked yet.",
            settings.license_renewal_url,
            exc,
            (seconds_left(current) or 0) / 86400,
        )
        _record(False, f"could not reach {settings.license_renewal_url}")
        return False

    if res.status_code == 402:
        # The subscription is genuinely over. Nothing to install, and nothing to
        # do: the key that is already here will run out on its own, and the gate
        # will say so in words.
        logger.info("renewal_declined reason=subscription_inactive")
        _record(False, "the subscription is no longer active")
        return False

    if res.status_code != 200:
        logger.warning("renewal_failed status=%s", res.status_code)
        _record(False, f"the renewal service answered {res.status_code}")
        return False

    try:
        fresh = (res.json() or {}).get("license_key", "")
    except Exception:  # noqa: BLE001
        logger.warning("renewal_failed reason=unreadable_response")
        _record(False, "the renewal service sent something unreadable")
        return False

    installed = apply_renewed_key(fresh)
    _record(installed, None if installed else "the new key was rejected")
    return installed
