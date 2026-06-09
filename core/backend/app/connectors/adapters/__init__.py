# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector adapters — real integrations (Stage A).

Each adapter authenticates a tenant against a source and `sync`s real records
into the growth tables (companies / contacts / leads). The flag-only behaviour
(``status=connected`` with no data) was the Stage-A gap; an adapter makes a
connector actually pull data that then flows to Lead Intelligence / Context
Graph / Dashboard.
"""

from app.connectors.adapters.base import (
    ConnectorAdapter,
    CredentialField,
    SyncResult,
)
from app.connectors.adapters.registry import get_adapter

__all__ = ["ConnectorAdapter", "CredentialField", "SyncResult", "get_adapter"]
