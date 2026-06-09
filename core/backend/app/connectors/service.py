# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector service — catalog + per-tenant connection state + real sync.

Stage A: a connector with a real adapter actually authenticates and syncs
records into the growth tables (companies/contacts/leads). Connectors without
an adapter keep the legacy flag-only connect so the catalog stays usable.
Credentials are Fernet-encrypted at rest (app.multitenant.crypto).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.connectors.adapters import get_adapter
from app.connectors.adapters.registry import has_adapter
from app.connectors.registry import get_connector, grouped
from app.db.growth_models import ConnectorState
from app.db.session import get_engine
from app.multitenant.crypto import decrypt_secret_value, encrypt_secret_value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _states(tenant_slug: str) -> Dict[str, ConnectorState]:
    with Session(get_engine()) as db:
        rows = list(
            db.exec(select(ConnectorState).where(
                ConnectorState.tenant_slug == tenant_slug))
        )
    return {r.connector_id: r for r in rows}


def _adapter_meta(connector_id: str) -> dict:
    """auth_kind + credential field specs for the connect form (UI)."""
    adp = get_adapter(connector_id)
    if adp is None:
        return {"has_adapter": False, "auth_kind": "none", "credential_fields": []}
    return {
        "has_adapter": True,
        "auth_kind": adp.auth_kind,
        "credential_fields": [
            {"key": f.key, "label": f.label, "type": f.type,
             "placeholder": f.placeholder, "required": f.required}
            for f in adp.credential_fields
        ],
    }


def list_connectors(*, tenant_slug: str) -> Dict[str, Any]:
    """Catalog grouped, each connector annotated with this tenant's status."""
    tenant_slug = (tenant_slug or "default").strip()
    states = _states(tenant_slug)
    groups = []
    connected = 0
    for g, label, conns in grouped():
        items = []
        for c in conns:
            st = states.get(c.id)
            d = c.to_dict()
            d["status"] = st.status if st else "available"
            d["health"] = st.health if st else None
            d["last_sync_at"] = st.last_sync_at.isoformat() if st and st.last_sync_at else None
            d["last_sync_count"] = st.last_sync_count if st else 0
            d["last_error"] = st.last_error if st else None
            d.update(_adapter_meta(c.id))
            if d["status"] == "connected":
                connected += 1
            items.append(d)
        groups.append({"key": g, "label": label, "connectors": items})
    return {"groups": groups, "connected_total": connected,
            "catalog_total": sum(len(c) for _, _, c in grouped())}


def connector_fields(connector_id: str) -> Optional[dict]:
    """Credential-field spec for one connector (None if unknown)."""
    if get_connector(connector_id) is None:
        return None
    return {"connector_id": connector_id, **_adapter_meta(connector_id)}


def _get_row(db: Session, tenant_slug: str, connector_id: str) -> Optional[ConnectorState]:
    return db.exec(
        select(ConnectorState).where(
            ConnectorState.tenant_slug == tenant_slug,
            ConnectorState.connector_id == connector_id,
        )
    ).first()


async def connect(
    *, tenant_slug: str, connector_id: str, credentials: Optional[dict] = None
) -> Optional[dict]:
    """Connect a connector. With a real adapter: test creds → store (encrypted,
    non-file) → run an initial sync. Without an adapter: legacy flag-only."""
    if get_connector(connector_id) is None:
        return None
    tenant_slug = (tenant_slug or "default").strip()
    credentials = credentials or {}
    adp = get_adapter(connector_id)

    if adp is not None:
        ok, msg = await adp.test_connection(credentials)
        if not ok:
            return {"connector_id": connector_id, "status": "error", "ok": False, "error": msg}
        with Session(get_engine()) as db:
            row = _get_row(db, tenant_slug, connector_id) or ConnectorState(
                tenant_slug=tenant_slug, connector_id=connector_id)
            row.status = "connected"
            row.health = 100
            row.connected_at = _now()
            row.auth_kind = adp.auth_kind
            # file-uploaded data is imported, not stored as a standing credential
            row.encrypted_credentials = (
                "" if adp.auth_kind == "file" else encrypt_secret_value(json.dumps(credentials))
            )
            row.last_error = None
            db.add(row)
            db.commit()
        sync_res = await sync(
            tenant_slug=tenant_slug, connector_id=connector_id,
            credentials_override=credentials,
        )
        return {"connector_id": connector_id, "status": "connected", "ok": True,
                "test_message": msg, "sync": sync_res}

    # legacy flag-only
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, connector_id) or ConnectorState(
            tenant_slug=tenant_slug, connector_id=connector_id)
        row.status = "connected"
        row.health = 100
        row.connected_at = _now()
        db.add(row)
        db.commit()
    return {"connector_id": connector_id, "status": "connected", "ok": True}


async def sync(
    *, tenant_slug: str, connector_id: str, credentials_override: Optional[dict] = None
) -> dict:
    """Run the connector's adapter sync → growth tables. Updates the row."""
    tenant_slug = (tenant_slug or "default").strip()
    adp = get_adapter(connector_id)
    if adp is None:
        return {"ok": False, "error": "no_adapter"}

    creds = credentials_override
    if creds is None:
        with Session(get_engine()) as db:
            row = _get_row(db, tenant_slug, connector_id)
            blob = row.encrypted_credentials if row else ""
        creds = json.loads(decrypt_secret_value(blob)) if blob else {}

    result = await adp.sync(tenant_slug, creds)
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, connector_id)
        if row:
            row.last_sync_at = _now()
            row.last_sync_count = result.total
            row.last_error = result.error or None
            row.health = 60 if result.error else 100
            db.add(row)
            db.commit()
    return {"ok": not result.error, **result.to_dict()}


def disconnect(*, tenant_slug: str, connector_id: str) -> Optional[dict]:
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = _get_row(db, tenant_slug, connector_id)
        if row is None:
            if get_connector(connector_id) is None:
                return None
            return {"connector_id": connector_id, "status": "available"}
        row.status = "available"
        row.encrypted_credentials = ""
        db.add(row)
        db.commit()
        return {"connector_id": connector_id, "status": "available"}


# keep has_adapter importable from the service namespace
__all__ = ["list_connectors", "connect", "disconnect", "sync", "connector_fields", "has_adapter"]
