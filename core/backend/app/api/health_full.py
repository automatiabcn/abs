# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""024 Modul H — Detailed health endpoint.

GET /v1/health/full — every dependency check (no live external API).
Output:
  {
    "ok": bool,
    "checks": [
      {"name": str, "ok": bool, "detail": str | dict | null}
    ]
  }
"""

from __future__ import annotations

import logging
import os
import shutil

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.session import get_engine

router = APIRouter(prefix="/v1/health", tags=["health"])
logger = logging.getLogger(__name__)


def _check_db() -> dict:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        return {
            "name": "database",
            "ok": result == 1,
            "detail": {"engine": str(engine.url)},
        }
    except Exception as exc:
        logger.exception("health_full database check failed")
        return {"name": "database", "ok": False, "detail": {"error_class": type(exc).__name__}}


def _check_vault() -> dict:
    try:
        sops = shutil.which("sops")
        age = shutil.which("age")
        configured = bool(sops and age)
        return {
            "name": "vault",
            "ok": True,  # absence is acceptable (console fallback)
            "detail": {
                "sops_binary": sops,
                "age_binary": age,
                "configured": configured,
            },
        }
    except Exception as exc:
        logger.exception("health_full vault check failed")
        return {"name": "vault", "ok": False, "detail": {"error_class": type(exc).__name__}}


def _check_providers() -> dict:
    """Each provider: env var presence (no live call)."""
    keys = {
        "anthropic": settings.anthropic_api_key,
        "groq": settings.groq_api_key,
        "cerebras": settings.cerebras_api_key,
        "gemini": settings.gemini_api_key,
        "cohere": settings.cohere_api_key,
        "cloudflare": bool(settings.cf_account_id and settings.cf_api_token),
    }
    configured = {k: bool(v) for k, v in keys.items()}
    return {
        "name": "providers",
        "ok": True,  # informational — no provider being configured is OK at boot
        "detail": configured,
    }


def _check_rag() -> dict:
    try:
        import importlib

        importlib.import_module("chromadb")
        return {"name": "rag", "ok": True, "detail": {"chromadb": "importable"}}
    except Exception as exc:
        logger.exception("health_full rag check failed")
        return {"name": "rag", "ok": False, "detail": {"error_class": type(exc).__name__}}


def _check_mcp() -> dict:
    try:
        from app.mcp.server import _REGISTERED_COUNT

        return {
            "name": "mcp",
            "ok": _REGISTERED_COUNT >= 100,
            "detail": {"registered_count": _REGISTERED_COUNT},
        }
    except Exception as exc:
        logger.exception("health_full mcp check failed")
        return {"name": "mcp", "ok": False, "detail": {"error_class": type(exc).__name__}}


def _check_email() -> dict:
    return {
        "name": "email",
        "ok": True,
        "detail": {
            "smtp_configured": bool(settings.smtp_host),
            "fallback": "console" if not settings.smtp_host else None,
        },
    }


def _check_data_dir() -> dict:
    return {
        "name": "data_dir",
        "ok": os.path.isdir(settings.data_dir) and os.access(settings.data_dir, os.W_OK),
        "detail": {"path": settings.data_dir},
    }


@router.get("/full")
async def health_full() -> dict:
    """024 — Aggregate dependency health (DB, vault, providers, RAG, MCP, email, data dir)."""
    checks = [
        _check_db(),
        _check_vault(),
        _check_providers(),
        _check_rag(),
        _check_mcp(),
        _check_email(),
        _check_data_dir(),
    ]
    overall = all(c["ok"] for c in checks)
    return {"ok": overall, "checks": checks}
