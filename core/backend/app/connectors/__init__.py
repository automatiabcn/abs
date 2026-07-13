# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector Layer — catalog + per-tenant connection state.

MCP-based, read-first, official-API-only (no scraping/ToS-violation). The
catalog mirrors the Connector Marketplace screen; per-tenant state records
which connectors a tenant has connected + their health.
"""

from app.connectors.registry import CONNECTORS, GROUP_LABELS, Connector, get_connector
from app.connectors.service import connect, disconnect, list_connectors

__all__ = [
    "CONNECTORS",
    "Connector",
    "get_connector",
    "GROUP_LABELS",
    "list_connectors",
    "connect",
    "disconnect",
]
