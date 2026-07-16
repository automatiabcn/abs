# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Shared account-identity fallback for the /v1/me/* self-service surfaces.

The GDPR self-service endpoints (data export, account deletion, consents,
personal audit log) authenticate a *customer* by their Bearer license token.
That is correct for a machine calling the API, but it locks out the person who
is already signed into the operator panel on their own self-host box: the panel
login uses a session cookie, not the raw license token, so the browser had no
way to call /v1/me/*.

On a self-host deployment the signed-in operator *is* the account holder, and
the server already holds exactly one license (`settings.license_key`). So when
a request carries no Bearer token but does carry a valid panel admin session,
we resolve the account identity from the server's own license. Destructive
actions (account deletion) still require the separate email-confirm token, so
this fallback never lets a session alone erase data.

Each me/* module keeps its own `_verify_bearer_license` with its own audit
action name (`me.account.auth`, `me.consent.auth`, ...) and its own return
shape; they call `panel_session_identity()` here only for the fallback branch,
preserving every existing Bearer-path emit and the `missing_bearer` denial that
the sweep tests pin.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from sqlmodel import Session, select

from app.config import settings
from app.db.models import License
from app.db.session import get_engine
from app.licensing import verify_license

logger = logging.getLogger(__name__)


def panel_session_identity(request: Optional[Request]) -> Optional[tuple[str, str]]:
    """Resolve (jti, customer_email) from a valid panel session, or None.

    Returns None (caller then denies as usual) when there is no request, no
    valid panel session, no server license, or the license won't verify. Never
    raises — a broken fallback must degrade to the normal Bearer denial, not a
    500.
    """
    if request is None:
        return None

    # Lazy import: admin.auth pulls in the panel auth module; importing it at
    # module load could cycle back through the API package.
    try:
        from app.api.admin.auth import _try_panel_session

        panel = _try_panel_session(request)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("panel-session fallback lookup skipped (non-fatal): %s", exc)
        return None
    if not panel:
        return None
    sub = str(panel.get("sub") or "")

    # Licensed self-host: attach me/* data to the server's license identity.
    key = getattr(settings, "license_key", "") or ""
    if key:
        try:
            claims = verify_license(key)
            jti = claims.get("jti")
            if jti:
                email = ""
                try:
                    with Session(get_engine()) as db:
                        row = db.scalars(
                            select(License).where(License.jti == jti)
                        ).first()
                        email = row.customer_email if row else ""
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("panel-session fallback: email lookup skipped: %s", exc)
                return jti, email or sub
        except Exception as exc:
            logger.debug("panel-session fallback: server license won't verify: %s", exc)

    # Keyless / trial self-host: no license row yet, so the operator's own
    # identity *is* the account — and it is exactly how customer actions are
    # already keyed before a license is issued (customer_audit_entries and
    # consents carry the admin email as their license_jti). Without this the
    # trial operator could never see their own consents or activity.
    if sub:
        return sub, sub
    return None
