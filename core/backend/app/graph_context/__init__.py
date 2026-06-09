# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Growth Context Graph + Entity Resolution (the moat).

Entity resolution merges duplicate firm records (Turkish-aware) into one
canonical Company; the context-graph view assembles companies + their
contacts / leads / opportunities into nodes + edges for the screen.
"""

from app.graph_context.service import (
    context_graph_view,
    normalize_company_name,
    resolve_companies,
)

__all__ = ["normalize_company_name", "resolve_companies", "context_graph_view"]
