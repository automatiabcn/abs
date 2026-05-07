# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Polish round R7 — provider key configuration status (no secrets exposed).

The Settings → Sağlayıcılar tab needs to render a status badge per provider
without ever shipping the raw API key to the browser. This endpoint reports
whether each cascade provider is configured (true/false) plus a small
``label`` map the UI can use as the canonical capitalised name.

GET /v1/admin/providers/status

Auth: ``admin_required``. Requires the admin Bearer token / cookie issued
by ``/v1/admin/auth/login`` — same surface as every other ``/v1/admin/*``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required
from app.config import settings

router = APIRouter(prefix="/v1/admin/providers", tags=["admin", "providers"])


# Canonical display labels + the settings attribute that holds each key.
# Capitalisation is owned by the backend so every consumer (UI, CLI,
# webhook payload) stays consistent; this also makes the wire payload the
# single source of truth instead of duplicating a label map in the React
# component.
_PROVIDERS: List[Dict[str, str]] = [
    {"id": "groq", "label": "Groq", "attr": "groq_api_key"},
    {"id": "cerebras", "label": "Cerebras", "attr": "cerebras_api_key"},
    {"id": "cloudflare", "label": "Cloudflare", "attr": "cf_api_token"},
    {"id": "gemini", "label": "Gemini", "attr": "gemini_api_key"},
    {"id": "cohere", "label": "Cohere", "attr": "cohere_api_key"},
    {"id": "anthropic", "label": "Anthropic", "attr": "anthropic_api_key"},
]


@router.get("/status")
async def providers_status(_admin: dict = Depends(admin_required)) -> Dict[str, Any]:
    """Return per-provider configured-or-not status without exposing keys."""
    items = []
    for spec in _PROVIDERS:
        raw = getattr(settings, spec["attr"], "") or ""
        configured = bool(raw.strip())
        items.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "configured": configured,
            }
        )
    return {"providers": items}
