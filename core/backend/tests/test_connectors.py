# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Connector Marketplace — catalog + per-tenant connect/disconnect."""

from __future__ import annotations

from app.connectors import CONNECTORS, list_connectors, connect, disconnect


def test_catalog_shape() -> None:
    assert len(CONNECTORS) == 27
    assert CONNECTORS["parasut"].local_priority is True   # Turkey niche
    out = list_connectors(tenant_slug="tCnew")
    assert out["catalog_total"] == 27
    assert out["connected_total"] == 0  # fresh tenant: nothing connected
    # everything starts "available"
    flat = [c for g in out["groups"] for c in g["connectors"]]
    assert all(c["status"] == "available" for c in flat)


def test_connect_disconnect_per_tenant() -> None:
    r = connect(tenant_slug="tC", connector_id="parasut")
    assert r["status"] == "connected"
    out = list_connectors(tenant_slug="tC")
    assert out["connected_total"] == 1
    parasut = next(
        c for g in out["groups"] for c in g["connectors"] if c["id"] == "parasut"
    )
    assert parasut["status"] == "connected"

    # idempotent
    assert connect(tenant_slug="tC", connector_id="parasut")["status"] == "connected"
    assert list_connectors(tenant_slug="tC")["connected_total"] == 1

    # isolation: another tenant unaffected
    assert list_connectors(tenant_slug="tC-other")["connected_total"] == 0

    disconnect(tenant_slug="tC", connector_id="parasut")
    assert list_connectors(tenant_slug="tC")["connected_total"] == 0


def test_unknown_connector() -> None:
    assert connect(tenant_slug="tC", connector_id="nope") is None
    assert disconnect(tenant_slug="tC", connector_id="nope") is None
