# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Connector Marketplace — catalog + per-tenant connect/disconnect.

Stage A made ``connect``/``sync`` async (a connector may authenticate + sync via
a real adapter); flag-only connectors still connect with no credentials.
"""

from __future__ import annotations

from app.connectors import CONNECTORS, connect, disconnect, list_connectors

CATALOG_TOTAL = len(CONNECTORS)


def test_catalog_shape() -> None:
    assert CATALOG_TOTAL == 28                        # 27 + csv_import (Stage A)
    assert CONNECTORS["parasut"].local_priority is True   # Turkey niche
    assert CONNECTORS["csv_import"].id == "csv_import"     # first real adapter
    out = list_connectors(tenant_slug="tCnew")
    assert out["catalog_total"] == CATALOG_TOTAL
    assert out["connected_total"] == 0  # fresh tenant: nothing connected
    # everything starts "available"
    flat = [c for g in out["groups"] for c in g["connectors"]]
    assert all(c["status"] == "available" for c in flat)
    # adapter metadata is surfaced for the connect form
    csv = next(c for c in flat if c["id"] == "csv_import")
    assert csv["has_adapter"] is True
    assert csv["auth_kind"] == "file"


async def test_connect_disconnect_per_tenant() -> None:
    r = await connect(tenant_slug="tC", connector_id="parasut")
    assert r["status"] == "connected"
    out = list_connectors(tenant_slug="tC")
    assert out["connected_total"] == 1
    parasut = next(
        c for g in out["groups"] for c in g["connectors"] if c["id"] == "parasut"
    )
    assert parasut["status"] == "connected"

    # idempotent
    assert (await connect(tenant_slug="tC", connector_id="parasut"))["status"] == "connected"
    assert list_connectors(tenant_slug="tC")["connected_total"] == 1

    # isolation: another tenant unaffected
    assert list_connectors(tenant_slug="tC-other")["connected_total"] == 0

    disconnect(tenant_slug="tC", connector_id="parasut")
    assert list_connectors(tenant_slug="tC")["connected_total"] == 0


async def test_unknown_connector() -> None:
    assert await connect(tenant_slug="tC", connector_id="nope") is None
    assert disconnect(tenant_slug="tC", connector_id="nope") is None


async def test_csv_import_dedups_within_file() -> None:
    from app.connectors.adapters.csv_import import CsvImportAdapter

    adp = CsvImportAdapter()
    csv = "company,score\nAkme A.Ş.,0.8\nAkme A.Ş.,0.9\nBeta Ltd,0.4"
    res = await adp.sync("tCsv", {"format": "csv", "data": csv})
    assert res.companies == 2          # 'Akme' deduped despite two rows
    assert res.leads == 2


def test_csv_import_caps_rows() -> None:
    from app.connectors.adapters.csv_import import _MAX_ROWS, _parse_rows

    big = "company\n" + "\n".join(f"Firma {i}" for i in range(_MAX_ROWS + 50))
    assert len(_parse_rows(big, "csv")) == _MAX_ROWS
