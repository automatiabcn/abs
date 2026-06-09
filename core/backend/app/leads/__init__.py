# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Lead Intelligence — companies, leads, scoring + account priority."""

from app.leads.service import (
    create_company,
    create_lead,
    get_lead,
    list_leads,
    score_lead,
)

__all__ = ["create_company", "create_lead", "score_lead", "list_leads", "get_lead"]
