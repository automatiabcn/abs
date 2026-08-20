# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Who may spend on a paid provider — one rule for every chain.

The product's money rule is simple to say: a paid provider runs on the key of
the person who is asking. Bring your own Anthropic key and Composer runs on
it first; bring nothing and you get the free chain. What the audit found
(2026-08-18) was the third case nobody had written down: the OPERATOR's paid
key, set in the server's environment. It was "configured", so
`get_active_providers` listed it; the deep-work ranking then put anthropic
ahead of every free provider; and any token on the server — a team member,
a delegated MCP token, `ask_opus` from a script — spent it, unmetered and
reported as `cost_free: true` when the pricing row was missing.

Rule, in order:
1. A caller's own key (BYOK) makes that paid provider theirs to use.
2. The server's paid keys are usable by the operator (the setup admin), who
   set them and pays the bill — a solo self-host loses nothing.
3. Anyone else may use the server's paid keys only if the operator said so:
   `ABS_PAID_SERVER_KEYS_SHARED=1`. Default: no.

`prefer=` names on a call are validated against this — asking for
"openrouter" is not a way around it.
"""

from __future__ import annotations

import os
from typing import FrozenSet, Iterable, List, Optional

from app.providers.cascade import PAID_PROVIDERS, is_configured


def _shared() -> bool:
    try:
        from app.config import settings

        v = getattr(settings, "paid_server_keys_shared", None)
        if v is not None:
            return bool(v)
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("ABS_PAID_SERVER_KEYS_SHARED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def is_operator(user_subject: Optional[str]) -> bool:
    """The setup admin — the person who configured the server's keys."""
    if not user_subject:
        return False
    try:
        from app.config import settings

        admin = str(getattr(settings, "admin_email", "") or "").strip().lower()
    except Exception:  # noqa: BLE001
        admin = ""
    if not admin:
        admin = os.environ.get("ABS_ADMIN_EMAIL", "").strip().lower()
    return bool(admin) and str(user_subject).strip().lower() == admin


def allowed_paid(
    byok: Iterable[str] = (), user_subject: Optional[str] = None
) -> FrozenSet[str]:
    """The paid providers THIS caller may run on."""
    mine = {p for p in byok if p in PAID_PROVIDERS}
    if _shared() or is_operator(user_subject):
        mine |= {p for p in PAID_PROVIDERS if is_configured(p)}
    return frozenset(mine)


def restrict_chain(
    chain: Iterable[str], byok: Iterable[str] = (), user_subject: Optional[str] = None
) -> List[str]:
    """`chain` without the paid providers this caller may not spend on."""
    ok = allowed_paid(byok, user_subject)
    return [p for p in chain if p not in PAID_PROVIDERS or p in ok]


def refusal(provider: str, byok: Iterable[str] = (), user_subject: Optional[str] = None) -> Optional[str]:
    """Why `provider` may not be used by this caller — or None."""
    if provider not in PAID_PROVIDERS:
        return None
    if provider in allowed_paid(byok, user_subject):
        return None
    if is_configured(provider):
        return (
            f"{provider} is a paid provider on the server's key; add your own "
            f"{provider} key to use it, or ask the operator to share the "
            f"server's (ABS_PAID_SERVER_KEYS_SHARED=1)."
        )
    return f"{provider} is a paid provider and no key for it is configured."
