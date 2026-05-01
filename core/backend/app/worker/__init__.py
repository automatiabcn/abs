"""T-002 — Inngest worker package.

Public surface:
  - inngest_client: shared Inngest client (singleton).
  - functions: list of registered Inngest functions discovered by the SDK.
  - bridge_nats_to_inngest: NATS subscriber that forwards events to Inngest.
"""

from app.worker.inngest_app import functions, inngest_client
from app.worker.nats_bridge import bridge_nats_to_inngest

__all__ = ["bridge_nats_to_inngest", "functions", "inngest_client"]
