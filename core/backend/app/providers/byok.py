# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""One place to ask "which providers did this caller bring a key for?".

The lookup itself lives in ``multitenant.provider_keys``; what belongs here
is the CONTRACT every caller needs and kept re-implementing slightly
differently: it never raises, an unknown caller is an empty set, and the
result is a frozenset ready for ``get_active_providers(extra_configured=…)``.

Two failures made this worth centralising, both found by auditing our own
changes (07-31 / 08-01):

* A path that forgets the lookup tells a user who has just pasted a key
  that no provider is configured — the panel asks them to fix something
  and then ignores the fix.
* Promoting a provider is only half the job. The chain says "your key is
  first" and the adapter still reads the operator's environment unless the
  KEY travels with the call — which is why :func:`owner_key_for` sits here
  next to it, so the two are found together.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def byok_providers(
    tenant_slug: Optional[str], user_subject: Optional[str] = None
) -> frozenset:
    """Providers this caller supplied their own key for. Never raises."""
    if not tenant_slug:
        return frozenset()
    try:
        from app.multitenant.provider_keys import tenant_configured_providers

        return frozenset(
            tenant_configured_providers(
                tenant_slug=tenant_slug, user_subject=user_subject
            )
        )
    except Exception as exc:  # noqa: BLE001 — BYOK is a bonus, never a blocker
        logger.debug("byok lookup skipped for %s: %s", tenant_slug, exc)
        return frozenset()


def owner_key_for(
    provider: str,
    *,
    tenant_slug: Optional[str],
    user_subject: Optional[str] = None,
) -> Optional[str]:
    """The caller's own key for one provider, or None. Never raises.

    Callers that go through ``call_with_cascade`` get this for free; anything
    that talks to an adapter directly (latency-sensitive paths) must ask here,
    or the promotion is a promise the credential never keeps.
    """
    if not (tenant_slug and (user_subject or tenant_slug)):
        return None
    try:
        from app.multitenant.provider_keys import resolve_provider_key

        return resolve_provider_key(
            provider,
            tenant_slug=tenant_slug,
            user_subject=user_subject,
            include_global=False,
        )
    except Exception as exc:  # noqa: BLE001 — never block a call on this
        logger.debug("owner key resolve skipped for %s: %s", provider, exc)
        return None
