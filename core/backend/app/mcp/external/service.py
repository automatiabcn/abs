# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""External MCP server registry — tenant-scoped CRUD + connection test.

Stores the servers a tenant added (``app/db/tenant_models.ExternalMcpServer``),
encrypts the auth secret at rest (``app.multitenant.crypto``) and never returns
the plaintext. ``test_connection`` drives the outbound client to discover the
server's tools and records a health snapshot on the row.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import ExternalMcpServer
from app.mcp.external import client as ext_client
from app.multitenant.crypto import decrypt_secret_value, encrypt_secret_value

logger = logging.getLogger(__name__)

_VALID_TRANSPORTS = frozenset({"http", "sse"})
_VALID_AUTH = frozenset({"none", "bearer", "header"})
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return s[:64] or "server"


def _public(row: ExternalMcpServer) -> dict:
    """Serialise a row for the API — NO secret material ever leaves here."""
    return {
        "slug": row.slug,
        "name": row.name,
        "url": row.url,
        "transport": row.transport,
        "auth_type": row.auth_type,
        "header_name": row.header_name,
        "has_auth": bool(row.encrypted_auth),
        "enabled": row.enabled,
        "status": row.status,
        "last_error": row.last_error,
        "discovered_tool_count": row.discovered_tool_count,
        "last_checked_at": row.last_checked_at.isoformat()
        if row.last_checked_at
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _validate(transport: str, auth_type: str, secret: str, header_name: str) -> None:
    if transport not in _VALID_TRANSPORTS:
        raise ValueError(f"invalid_transport: {transport}")
    if auth_type not in _VALID_AUTH:
        raise ValueError(f"invalid_auth_type: {auth_type}")
    if auth_type == "bearer" and not secret:
        raise ValueError("bearer_auth_requires_token")
    if auth_type == "header" and (not secret or not header_name):
        raise ValueError("header_auth_requires_name_and_value")
    # Fail fast on an unsafe URL at write time (re-checked at connect time too).


def add_server(
    *,
    tenant_slug: str,
    name: str,
    url: str,
    transport: str = "http",
    auth_type: str = "none",
    secret: str = "",
    header_name: str = "",
    created_by: str = "",
) -> dict:
    """Insert a new external MCP server for the tenant. Returns the public dict."""
    name = (name or "").strip()
    url = (url or "").strip()
    if not name:
        raise ValueError("name_required")
    if not url:
        raise ValueError("url_required")
    secret = (secret or "").strip()
    header_name = (header_name or "").strip()
    _validate(transport, auth_type, secret, header_name)
    ext_client._assert_safe_url(url)  # reject SSRF targets before persisting

    slug = slugify(name)
    enc = encrypt_secret_value(secret) if secret else ""

    with Session(get_engine()) as db:
        # Unique per (tenant, slug); disambiguate by suffixing.
        base, n = slug, 2
        while db.exec(
            select(ExternalMcpServer).where(
                ExternalMcpServer.tenant_slug == tenant_slug,
                ExternalMcpServer.slug == slug,
            )
        ).first():
            slug = f"{base}-{n}"[:64]
            n += 1
        row = ExternalMcpServer(
            tenant_slug=tenant_slug,
            slug=slug,
            name=name,
            url=url,
            transport=transport,
            auth_type=auth_type,
            encrypted_auth=enc,
            header_name=header_name,
            enabled=True,
            status="unconfigured",
            discovered_tool_count=0,
            created_at=_now(),
            created_by=created_by or "",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "external_mcp_added tenant=%s slug=%s transport=%s auth=%s by=%s",
            tenant_slug,
            slug,
            transport,
            auth_type,
            created_by,
        )
        return _public(row)


def list_servers(tenant_slug: str) -> list[dict]:
    with Session(get_engine()) as db:
        rows = db.exec(
            select(ExternalMcpServer)
            .where(ExternalMcpServer.tenant_slug == tenant_slug)
            .order_by(ExternalMcpServer.created_at)
        ).all()
        return [_public(r) for r in rows]


def _get_row(db: Session, tenant_slug: str, slug: str) -> Optional[ExternalMcpServer]:
    return db.exec(
        select(ExternalMcpServer).where(
            ExternalMcpServer.tenant_slug == tenant_slug,
            ExternalMcpServer.slug == slug,
        )
    ).first()


def get_server(tenant_slug: str, slug: str) -> Optional[dict]:
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        return _public(row) if row else None


def update_server(
    *,
    tenant_slug: str,
    slug: str,
    name: Optional[str] = None,
    url: Optional[str] = None,
    transport: Optional[str] = None,
    auth_type: Optional[str] = None,
    secret: Optional[str] = None,  # None=unchanged, ""=clear, value=rotate
    header_name: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict]:
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        if not row:
            return None
        if name is not None:
            row.name = name.strip() or row.name
        if url is not None and url.strip():
            ext_client._assert_safe_url(url.strip())
            row.url = url.strip()
        if transport is not None:
            row.transport = transport
        if auth_type is not None:
            row.auth_type = auth_type
        if header_name is not None:
            row.header_name = header_name.strip()
        if secret is not None:
            row.encrypted_auth = (
                encrypt_secret_value(secret.strip()) if secret.strip() else ""
            )
        if enabled is not None:
            row.enabled = bool(enabled)
        # Re-validate the resulting auth shape.
        _validate(
            row.transport,
            row.auth_type,
            decrypt_secret_value(row.encrypted_auth) if row.encrypted_auth else "",
            row.header_name,
        )
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return _public(row)


def remove_server(tenant_slug: str, slug: str) -> bool:
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        if not row:
            return False
        db.delete(row)
        db.commit()
        logger.info("external_mcp_removed tenant=%s slug=%s", tenant_slug, slug)
        return True


def connection_params(tenant_slug: str, slug: str) -> Optional[dict]:
    """Return the live connection details (decrypted headers) for federation.

    NOT exposed by the API — internal use by the federation layer only.
    """
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        if not row:
            return None
        secret = decrypt_secret_value(row.encrypted_auth) if row.encrypted_auth else ""
        return {
            "tenant_slug": row.tenant_slug,
            "slug": row.slug,
            "name": row.name,
            "url": row.url,
            "transport": row.transport,
            "enabled": row.enabled,
            "headers": ext_client.build_headers(row.auth_type, secret, row.header_name),
        }


def list_enabled_for_federation() -> list[dict]:
    """All enabled servers across every tenant (single-tenant deployment use)."""
    with Session(get_engine()) as db:
        rows = db.exec(
            select(ExternalMcpServer).where(ExternalMcpServer.enabled == True)  # noqa: E712
        ).all()
        return [{"tenant_slug": r.tenant_slug, "slug": r.slug} for r in rows]


async def test_connection(tenant_slug: str, slug: str) -> dict:
    """Connect to the server, discover tools, persist a health snapshot."""
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        if not row:
            return {"ok": False, "error": "not_found"}
        url, transport, auth_type = row.url, row.transport, row.auth_type
        header_name = row.header_name
        secret = decrypt_secret_value(row.encrypted_auth) if row.encrypted_auth else ""

    headers = ext_client.build_headers(auth_type, secret, header_name)
    result: dict
    try:
        tools = await ext_client.discover_tools(url, transport, headers)
        result = {
            "ok": True,
            "tool_count": len(tools),
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        }
        status, last_error, count = "ok", None, len(tools)
    except ext_client.ExternalMcpError as exc:
        result = {"ok": False, "error": str(exc)}
        status, last_error, count = "error", str(exc)[:512], 0

    # Persist the snapshot.
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, slug)
        if row:
            row.status = status
            row.last_error = last_error
            row.discovered_tool_count = count
            row.last_checked_at = _now()
            db.add(row)
            db.commit()
    return result
