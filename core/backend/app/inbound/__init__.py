# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Inbound Intelligence — classify an incoming request + draft a sourced reply.

MVP slice: the Inbound Triage Agent classifies intent, the runtime grounds a
reply in the tenant's RAG corpus (source-cited), and the medium-risk draft lands
in the Approval Center. Outbound (the legally-risky direction) never auto-sends.
"""

from app.inbound.service import INTENTS, triage_inbound

__all__ = ["triage_inbound", "INTENTS"]
