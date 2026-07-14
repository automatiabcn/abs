# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Per-owner provider key management (multi-tenant Phase 1).

Lets an admin store/list/delete provider API keys scoped to an owner —
``user`` (a teammate's own key), ``project`` (a workspace key), or ``org``
(tenant-wide). Keys are encrypted at rest (app.multitenant.crypto) and resolved
at request time project → user → org → global by app.multitenant.provider_keys.

This is the management surface for the BYOK model — each user brings their own
key. Tenant-scoped: a caller only ever touches their own tenant's
rows. Plaintext is never returned.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.admin.auth import admin_required
from app.multitenant import provider_keys as pk
from app.observability.audit import emit_event
from app.providers.cascade import SETTINGS_KEY_ATTR


def _resolve_admin_tenant(admin: dict) -> str:
    """Resolve the admin's tenant the SAME way the runtime RAG/cascade path does
    (`auth.tenant_id` ← `_resolve_tenant`). Using the marketplace resolver here
    diverged (domain heuristic → a per-domain slug) from the runtime tenant ("default"
    where the data lives), so panel-stored keys/projects were never found at
    request time. Aligning both ends keeps BYOK + project scoping consistent."""
    from app.api.chat import _resolve_tenant

    return (
        _resolve_tenant(str(admin.get("sub") or admin.get("email") or "")) or "default"
    )


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/provider-keys", tags=["admin", "provider-keys"])

_VALID_PROVIDERS = frozenset(SETTINGS_KEY_ATTR.keys())


def _admin_subject(admin: dict) -> str:
    return str(admin.get("sub") or admin.get("email") or "").strip()


class ProviderKeyIn(BaseModel):
    provider: str = Field(..., min_length=2, max_length=32)
    value: str = Field(..., min_length=4, max_length=8192)
    owner_type: str = Field(default=pk.OWNER_USER)  # user | project | org
    # For owner_type=user, defaults to the calling admin's own subject; for org,
    # defaults to the tenant slug. Required for project.
    owner_id: str | None = Field(default=None, max_length=128)


class ProviderKeyDel(BaseModel):
    provider: str = Field(..., min_length=2, max_length=32)
    owner_type: str = Field(default=pk.OWNER_USER)
    owner_id: str | None = Field(default=None, max_length=128)


class ProviderKeyTest(BaseModel):
    provider: str = Field(..., min_length=2, max_length=32)
    owner_type: str = Field(default=pk.OWNER_USER)
    owner_id: str | None = Field(default=None, max_length=128)
    # Optional: validate a raw key BEFORE saving it. When omitted, the stored
    # key for this owner is tested.
    value: str | None = Field(default=None, max_length=8192)


async def _ping_provider(
    provider: str, key: str, tenant: str
) -> tuple[bool, str | None]:
    """Live one-shot ping of a provider with a SPECIFIC key (api_key override).
    Returns (ok, reason). Never raises — a bad key is a result, not a 500."""
    import asyncio

    try:
        from app.cascade.orchestrator import call_with_cascade

        resp = await asyncio.wait_for(
            call_with_cascade(
                "ping",
                primary=provider,
                fallbacks=(),
                use_cache=False,
                tenant_id=tenant or "_global",
                api_key=key,
                max_tokens=4,
            ),
            timeout=12.0,
        )
        text = getattr(resp, "text", "") or ""
        return (bool(text), None if text else "empty response")
    except Exception as exc:  # noqa: BLE001 — bad key / timeout → fail result
        return (False, _explain(provider, exc))


# What the customer saw when a key was wrong, verbatim, in the panel:
#
#   ✗ Cohere UnauthorizedError: headers: {'cache-control': 'no-cache, no-store,
#     no-transform, must-revalidate, private, max-age=0', 'content-encoding':
#     'gzip', 'conte…
#
# — the provider SDK's exception with its HTTP response headers, truncated
# mid-word. It says nothing about what to do, and it publishes our internals to
# someone who was only trying to paste an API key. The exception is still logged;
# what comes back is a sentence.
def _explain(provider: str, exc: Exception) -> str:
    name = provider.capitalize()
    blob = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in blob or isinstance(exc, TimeoutError):
        return f"{name} did not answer in time. Try again, or check the key later."
    if "unauthor" in blob or "401" in blob or "invalid api key" in blob:
        return f"{name} rejected this key. Check you copied all of it."
    if "forbidden" in blob or "403" in blob:
        return f"{name} accepted the key but refused the request — it may not have access to this model."
    if "429" in blob or "rate limit" in blob or "quota" in blob:
        return f"{name} says this key is out of quota right now."
    if "not found" in blob or "404" in blob:
        return f"{name} could not find the account or model this key belongs to."
    logger.warning("provider_key_probe_failed provider=%s error=%s", provider, exc)
    return f"{name} refused the key, and did not say why."


def _resolve_owner(
    admin: dict, tenant: str, owner_type: str, owner_id: str | None
) -> str:
    owner_type = (owner_type or "").strip()
    if owner_type == pk.OWNER_ORG:
        return tenant
    if owner_type == pk.OWNER_USER:
        return (owner_id or "").strip() or _admin_subject(admin)
    if owner_type == pk.OWNER_PROJECT:
        oid = (owner_id or "").strip()
        if not oid:
            raise HTTPException(422, "owner_id_required_for_project")
        return oid
    raise HTTPException(422, f"invalid_owner_type: {owner_type}")


@router.get("")
async def list_keys(admin: dict = Depends(admin_required)) -> dict:
    tenant = _resolve_admin_tenant(admin)
    return {"tenant": tenant, "keys": pk.list_provider_keys(tenant_slug=tenant)}


@router.post("")
async def set_key(body: ProviderKeyIn, admin: dict = Depends(admin_required)) -> dict:
    if body.provider not in _VALID_PROVIDERS:
        raise HTTPException(422, f"unknown_provider: {body.provider}")
    tenant = _resolve_admin_tenant(admin)
    owner_id = _resolve_owner(admin, tenant, body.owner_type, body.owner_id)
    try:
        pk.set_provider_key(
            tenant_slug=tenant,
            owner_type=body.owner_type,
            owner_id=owner_id,
            provider=body.provider,
            value=body.value,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    logger.info(
        "provider_key_set tenant=%s owner=%s:%s provider=%s by=%s",
        tenant,
        body.owner_type,
        owner_id,
        body.provider,
        _admin_subject(admin),
    )
    # Someone put a credential on this server that can spend the company's money.
    # The line above says so to stderr; this one says it to the log a person can
    # actually open. (The key itself never travels — provider and owner only.)
    emit_event(
        None,
        action="provider_key.set",
        outcome="success",
        provider=body.provider,
        resource_type=body.owner_type,
        resource_id=owner_id,
        user_id=_admin_subject(admin),
        tenant_id=tenant,
    )
    return {
        "ok": True,
        "owner_type": body.owner_type,
        "owner_id": owner_id,
        "provider": body.provider,
    }


@router.post("/test")
async def test_key(
    body: ProviderKeyTest, admin: dict = Depends(admin_required)
) -> dict:
    """Live-validate a BYOK provider key — either a raw value (pre-save check)
    or the stored key for this owner. On a stored key, the result is persisted
    to last_validated_ok/at so the panel can show a freshness badge."""
    if body.provider not in _VALID_PROVIDERS:
        raise HTTPException(422, f"unknown_provider: {body.provider}")
    tenant = _resolve_admin_tenant(admin)
    owner_id = _resolve_owner(admin, tenant, body.owner_type, body.owner_id)
    raw = (body.value or "").strip()
    key = raw or pk.get_owner_key(
        tenant_slug=tenant,
        owner_type=body.owner_type,
        owner_id=owner_id,
        provider=body.provider,
    )
    if not key:
        raise HTTPException(404, "no_key_to_test")
    ok, reason = await _ping_provider(body.provider, key, tenant)
    if not raw:
        # only persist validation state for a STORED key (not a pre-save probe)
        pk.mark_key_validated(
            tenant_slug=tenant,
            owner_type=body.owner_type,
            owner_id=owner_id,
            provider=body.provider,
            ok=ok,
        )
    logger.info(
        "provider_key_test tenant=%s owner=%s:%s provider=%s ok=%s by=%s",
        tenant,
        body.owner_type,
        owner_id,
        body.provider,
        ok,
        _admin_subject(admin),
    )
    return {
        "ok": ok,
        "provider": body.provider,
        "reason": reason,
        "owner_type": body.owner_type,
        "owner_id": owner_id,
    }


@router.delete("")
async def delete_key(
    body: ProviderKeyDel, admin: dict = Depends(admin_required)
) -> dict:
    tenant = _resolve_admin_tenant(admin)
    owner_id = _resolve_owner(admin, tenant, body.owner_type, body.owner_id)
    removed = pk.delete_provider_key(
        tenant_slug=tenant,
        owner_type=body.owner_type,
        owner_id=owner_id,
        provider=body.provider,
    )
    # A credential was taken off this server. "Who removed our Groq key, and
    # when?" is a question that gets asked on a bad day, and it needs an answer.
    emit_event(
        None,
        action="provider_key.delete",
        outcome="success" if removed else "failure",
        provider=body.provider,
        resource_type=body.owner_type,
        resource_id=owner_id,
        user_id=_admin_subject(admin),
        tenant_id=tenant,
    )
    return {"ok": removed, "deleted": removed}
