# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector service — catalog + per-tenant connection state. Tenant-scoped."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.connectors.registry import GROUP_LABELS, get_connector, grouped
from app.db.growth_models import ConnectorState
from app.db.session import get_engine


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _states(tenant_slug: str) -> Dict[str, ConnectorState]:
    with Session(get_engine()) as db:
        rows = list(
            db.exec(select(ConnectorState).where(
                ConnectorState.tenant_slug == tenant_slug))
        )
    return {r.connector_id: r for r in rows}


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
            d["last_sync_at"] = (
                st.last_sync_at.isoformat() if st and st.last_sync_at else None
            )
            if d["status"] == "connected":
                connected += 1
            items.append(d)
        groups.append({"key": g, "label": label, "connectors": items})
    return {"groups": groups, "connected_total": connected,
            "catalog_total": sum(len(c) for _, _, c in grouped())}


def connect(*, tenant_slug: str, connector_id: str) -> Optional[dict]:
    """Mark a catalog connector connected for this tenant (idempotent)."""
    if get_connector(connector_id) is None:
        return None
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.exec(
            select(ConnectorState).where(
                ConnectorState.tenant_slug == tenant_slug,
                ConnectorState.connector_id == connector_id,
            )
        ).first()
        if row is None:
            row = ConnectorState(tenant_slug=tenant_slug, connector_id=connector_id)
        row.status = "connected"
        row.health = 100
        row.connected_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"connector_id": row.connector_id, "status": row.status,
                "health": row.health}


def disconnect(*, tenant_slug: str, connector_id: str) -> Optional[dict]:
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.exec(
            select(ConnectorState).where(
                ConnectorState.tenant_slug == tenant_slug,
                ConnectorState.connector_id == connector_id,
            )
        ).first()
        if row is None:
            if get_connector(connector_id) is None:
                return None
            return {"connector_id": connector_id, "status": "available"}
        row.status = "available"
        db.add(row)
        db.commit()
        return {"connector_id": connector_id, "status": "available"}
