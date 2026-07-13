# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Adapter registry — connector_id → real adapter.

Connectors with no adapter yet fall back to flag-only connect (legacy). As real
adapters land (HubSpot OAuth, ERP APIs, …) they register here and the same
connect/sync plumbing makes them pull real data.
"""

from __future__ import annotations

from typing import Optional

from app.connectors.adapters.base import ConnectorAdapter
from app.connectors.adapters.csv_import import CsvImportAdapter

_ADAPTERS: dict[str, ConnectorAdapter] = {
    CsvImportAdapter.connector_id: CsvImportAdapter(),
}


def get_adapter(connector_id: str) -> Optional[ConnectorAdapter]:
    return _ADAPTERS.get((connector_id or "").strip())


def has_adapter(connector_id: str) -> bool:
    return (connector_id or "").strip() in _ADAPTERS
