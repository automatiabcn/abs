# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Inngest worker package.

Public surface:
  - inngest_client: shared Inngest client (singleton).
  - functions: list of registered Inngest functions discovered by the SDK.
  - bridge_nats_to_inngest: NATS subscriber that forwards events to Inngest.
"""

from app.worker.inngest_app import functions, inngest_client
from app.worker.nats_bridge import bridge_nats_to_inngest

__all__ = ["bridge_nats_to_inngest", "functions", "inngest_client"]
