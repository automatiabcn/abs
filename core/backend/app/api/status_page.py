# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Public status page.

GET /v1/status         — JSON (services, overall, uptime, version)
GET /status            — HTML page with 30s auto-refresh

7 service checks: db, vault, providers, rag, mcp, email, stripe.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import hmac
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["status"])

# Process boot time for uptime calculation
_BOOT_TIME = time.time()
_VERSION = settings.version

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _check_db() -> dict:
    try:
        from sqlalchemy import text

        from app.db.session import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
        return {"name": "database", "ok": True}
    except Exception as exc:
        logger.exception("status_page database check failed")
        return {"name": "database", "ok": False, "error_class": type(exc).__name__}


def _check_vault() -> dict:
    import shutil

    return {
        "name": "vault",
        "ok": True,  # console fallback acceptable
        "configured": bool(shutil.which("sops") and shutil.which("age")),
    }


def _check_providers() -> dict:
    """Can this server answer a question at all?

    It used to be hardcoded `ok: True`, with the comment that having no provider
    configured is fine at boot. At boot, yes. Afterwards it means the one thing the
    product promises — ask it something, get an answer — cannot happen, and the
    health check said everything was fine.

    Key *presence* is still all this measures; a revoked or mistyped key reads as
    configured. The live signal exists (app/health/monitor.py pings every provider
    every 60 seconds) and neither status endpoint consults it — worth wiring up,
    and a bigger change than this one. Until then this at least stops reporting a
    server with nothing configured as healthy.
    """
    configured_count = sum(
        1
        for v in (
            settings.anthropic_api_key,
            settings.groq_api_key,
            settings.cerebras_api_key,
            settings.gemini_api_key,
            settings.cohere_api_key,
            settings.cf_account_id and settings.cf_api_token,
        )
        if v
    )
    result: dict = {
        "name": "providers",
        "ok": configured_count > 0,
        "configured_count": configured_count,
    }
    if configured_count == 0:
        result["detail"] = (
            "no provider is configured — this server cannot answer a question"
        )
    return result


def _check_rag() -> dict:
    """Is document search actually working?

    This used to be `import chromadb` — a check on whether a library was
    installed, standing in for a check on whether the feature worked. It
    reported `ok` while the embedding backend was the mock one, which is to say
    while every question put to the knowledge base was being answered from five
    unrelated chunks. A health check that is green during the outage it exists to
    report is worse than no health check: it is the reason nobody looks further.

    So it asks the question the operator is actually asking: can this server find
    the right document?
    """
    try:
        import importlib

        importlib.import_module("chromadb")
    except Exception:
        return {"name": "rag", "ok": False, "detail": "vector store unavailable"}

    try:
        from app.rag.embedding_bge import get_embedder

        embedder = get_embedder()
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "rag",
            "ok": False,
            "detail": f"embedding backend unavailable: {str(exc)[:120]}",
        }

    if not embedder.semantic:
        return {
            "name": "rag",
            "ok": False,
            "embed_model": embedder.model_id(),
            "detail": (
                "no embedding model configured — documents can be uploaded but "
                "not searched. Set ABS_EMBEDDING_BACKEND."
            ),
        }
    return {"name": "rag", "ok": True, "embed_model": embedder.model_id()}


def _check_mcp() -> dict:
    try:
        from app.mcp.server import _REGISTERED_COUNT

        return {
            "name": "mcp",
            "ok": _REGISTERED_COUNT >= 100,
            "tools": _REGISTERED_COUNT,
        }
    except Exception as exc:
        logger.exception("status_page mcp check failed")
        return {"name": "mcp", "ok": False, "error_class": type(exc).__name__}


def _check_email() -> dict:
    return {
        "name": "email",
        "ok": True,
        "transport": "smtp" if settings.smtp_host else "console",
    }


def _check_stripe() -> dict:
    return {
        "name": "stripe",
        "ok": True,
        "configured": bool(settings.stripe_secret_key),
    }


@router.get("/v1/status")
async def status_json() -> dict:
    """025 — Public status JSON. No auth (used by uptime monitors)."""
    services = [
        _check_db(),
        _check_vault(),
        _check_providers(),
        _check_rag(),
        _check_mcp(),
        _check_email(),
        _check_stripe(),
    ]
    # Severity, not arithmetic. This used to count failures: zero was "ok", one or
    # two "degraded", three or more "down". Four of the seven checks were hardcoded
    # to pass, so they padded the denominator and nothing else — and a server whose
    # database was unreachable, which can do precisely nothing, was reported as
    # "degraded" because only one box had gone red.
    #
    # Some failures are not partial. Without the database there is no server, and
    # without a provider there is no answer; those are the two things a customer
    # would call an outage, so they are the two things that say so.
    CRITICAL = {"database", "providers"}
    failed = [s["name"] for s in services if not s["ok"]]
    if not failed:
        overall = "ok"
    elif CRITICAL.intersection(failed):
        overall = "down"
    else:
        overall = "degraded"
    return {
        "overall": overall,
        "uptime_seconds": int(time.time() - _BOOT_TIME),
        "version": _VERSION,
        "services": services,
    }


def _licenses_active_count() -> int:
    try:
        from datetime import datetime, timezone

        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        now = datetime.now(timezone.utc)
        with Session(get_engine()) as db:
            rows = db.scalars(select(License)).all()
        return sum(
            1
            for r in rows
            if r.revoked_at is None
            and r.purged_at is None
            and (
                r.expires_at is None
                or (
                    (
                        r.expires_at.replace(tzinfo=timezone.utc)
                        if r.expires_at.tzinfo is None
                        else r.expires_at
                    )
                    > now
                )
            )
        )
    except Exception:
        return 0


def _signups_24h_count() -> int:
    try:
        from datetime import datetime, timedelta, timezone

        from sqlmodel import Session, select

        from app.db.models import BetaRequest, License
        from app.db.session import get_engine

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with Session(get_engine()) as db:
            beta = list(db.scalars(select(BetaRequest)).all())
            paid = list(db.scalars(select(License)).all())
        count = 0
        for r in beta:
            ts = r.created_at
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    count += 1
        for r in paid:
            ts = r.issued_at
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff and r.tier and r.tier != "beta":
                    count += 1
        return count
    except Exception:
        return 0


def _last_payment_iso() -> Optional[str]:
    try:
        from datetime import timezone

        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            rows = list(db.scalars(select(License)).all())
        paid = [r for r in rows if r.tier and r.tier != "beta"]
        if not paid:
            return None
        ts = max(r.issued_at for r in paid if r.issued_at is not None)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    except Exception:
        return None


def _mrr_estimate_usd() -> int:
    """Rough MRR: tier × active-license heuristic. Per-tier monthly contribution
    comes from settings (Q12-R84 — operator configures real prices)."""
    try:
        from sqlmodel import Session, select

        from app.config import settings as _s
        from app.db.models import License
        from app.db.session import get_engine

        # Heuristic share of seat-pack list price counted per active license per
        # month. Defaults are 0.0 — operator configures via env to surface MRR.
        # Keyed by (tier, seat_count) — the License.tier value is "self-host" /
        # "team" (seat_count distinguishes the 5- vs 10-pack), NOT "team-5".
        # The old "team-5"/"team-10" string keys never matched a real tier, so
        # every team licence silently contributed $0 to MRR. Matches the
        # (tier, seat_count) convention in billing_tools / status_tools.
        TIER_MONTHLY: dict[tuple[str, int], float] = {
            ("self-host", 1): _s.abs_seat_price_self_host / 12.0,
            ("team", 5): _s.abs_seat_price_team_5 / 12.0,
            ("team", 10): _s.abs_seat_price_team_10 / 12.0,
        }
        with Session(get_engine()) as db:
            rows = list(db.scalars(select(License)).all())
        total = 0.0
        for r in rows:
            key = (r.tier, r.seat_count)
            if key in TIER_MONTHLY and r.revoked_at is None and r.purged_at is None:
                total += TIER_MONTHLY[key]
        return int(round(total))
    except Exception:
        return 0


def _panel_session_is_admin(request) -> bool:
    """Accept a panel session: a self-hosted install may have only one admin."""
    if request is None:
        return False
    try:
        from app.api import auth as panel_auth_mod

        token = request.cookies.get(panel_auth_mod.COOKIE_NAME, "")
        if not token:
            return False
        payload = panel_auth_mod._decode_token(token)
        admin_email, _hash, _src = panel_auth_mod._load_admin_credentials()
        return payload.get("sub") == admin_email
    except Exception:
        return False


def _require_admin(authorization: Optional[str], request=None) -> None:
    if _panel_session_is_admin(request):
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "admin_bearer_required")
    parts = authorization.split(None, 1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if not token:
        raise HTTPException(401, "admin_bearer_required")
    expected = settings.beta_admin_token or ""
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "admin_token_invalid")


@router.get("/v1/admin/status/full")
async def admin_status_full(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """031 — Admin-only enriched status: revenue, signups, recent activity."""
    _require_admin(authorization, request)
    base = await status_json()
    base["licenses_active"] = _licenses_active_count()
    base["mrr_estimate_usd"] = _mrr_estimate_usd()
    base["signups_24h"] = _signups_24h_count()
    base["last_payment_at"] = _last_payment_iso()
    return base


@router.get("/status", include_in_schema=False)
async def status_html() -> FileResponse:
    """Static HTML status page (30s auto-refresh)."""
    return FileResponse(_STATIC_DIR / "status.html", media_type="text/html")
