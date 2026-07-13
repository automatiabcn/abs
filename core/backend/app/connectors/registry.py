# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector catalog — the marketplace's available integrations.

Read-first, official-API / approved-channel only. ``kind`` is read|write|action;
``official`` flags an official API vs an approved provider (BSP). Grouped to
mirror the Connector Marketplace screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

GRP_ERP = "erp"
GRP_CRM = "crm"
GRP_COMMS = "comms_ads"
GRP_DATA = "data_automation"

GROUP_LABELS = {
    GRP_ERP: "ERP / Bookkeeping",
    GRP_CRM: "CRM",
    GRP_COMMS: "Communication & Ads",
    GRP_DATA: "Data / Intelligence / Automation",
}


@dataclass(frozen=True)
class Connector:
    id: str
    name: str
    group: str
    kind: str                 # read | read/write | action
    note: str = ""
    official: bool = True      # official API / approved channel (no scraping)
    local_priority: bool = False  # regional integration a global vendor rarely ships

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "group": self.group,
            "kind": self.kind, "note": self.note, "official": self.official,
            "local_priority": self.local_priority,
        }


def _c(**kw) -> Connector:
    return Connector(**kw)


_LIST: List[Connector] = [
    # Regional ERP / bookkeeping vendors. The first name is the vendor's own
    # brand, escaped so the source stays ASCII — it is a proper noun, not copy.
    _c(id="parasut", name="Para\u015f\u00fct", group=GRP_ERP, kind="read", note="invoice + payment", local_priority=True),
    _c(id="logo", name="Logo", group=GRP_ERP, kind="read", note="revenue sync", local_priority=True),
    _c(id="mikro", name="Mikro", group=GRP_ERP, kind="read", note="customer + order", local_priority=True),
    _c(id="erpnext", name="ERPNext", group=GRP_ERP, kind="read/write"),
    _c(id="quickbooks", name="QuickBooks", group=GRP_ERP, kind="read", note="invoice"),
    _c(id="xero", name="Xero", group=GRP_ERP, kind="read", note="revenue"),
    # CRM
    _c(id="hubspot", name="HubSpot", group=GRP_CRM, kind="read", note="contact + deal"),
    _c(id="salesforce", name="Salesforce", group=GRP_CRM, kind="read/write"),
    _c(id="zoho", name="Zoho CRM", group=GRP_CRM, kind="read", note="pipeline"),
    _c(id="pipedrive", name="Pipedrive", group=GRP_CRM, kind="read", note="deal"),
    _c(id="frappe_crm", name="Frappe CRM", group=GRP_CRM, kind="read/write"),
    _c(id="internal_crm", name="Internal CRM", group=GRP_CRM, kind="read/write", note="lightweight schema"),
    # Communication & ads — approved channels only, never a scraped one.
    _c(id="gmail", name="Gmail", group=GRP_COMMS, kind="read", note="read inbound"),
    _c(id="microsoft365", name="Microsoft 365", group=GRP_COMMS, kind="read"),
    _c(id="whatsapp_bsp", name="WhatsApp BSP", group=GRP_COMMS, kind="action", note="approved API"),
    _c(id="twilio", name="Twilio", group=GRP_COMMS, kind="action", note="SMS / voice"),
    _c(id="google_ads", name="Google Ads", group=GRP_COMMS, kind="read", note="attribution"),
    _c(id="meta_ads", name="Meta Ads", group=GRP_COMMS, kind="read", note="attribution"),
    _c(id="linkedin_ads", name="LinkedIn Ads", group=GRP_COMMS, kind="action", note="audience"),
    _c(id="slack_teams", name="Slack / Teams", group=GRP_COMMS, kind="read", note="read export"),
    # Data / Intelligence / Automation
    _c(id="firecrawl", name="Firecrawl", group=GRP_DATA, kind="read", note="web crawl (ToS-safe)"),
    _c(id="apify", name="Apify", group=GRP_DATA, kind="read", note="official-API scrape"),
    _c(id="clay", name="Clay", group=GRP_DATA, kind="read", note="enrichment"),
    _c(id="apollo", name="Apollo", group=GRP_DATA, kind="read", note="lead data"),
    _c(id="zoominfo", name="ZoomInfo", group=GRP_DATA, kind="read", note="enrichment"),
    _c(id="n8n", name="n8n", group=GRP_DATA, kind="action", note="middleware automation"),
    _c(id="custom_mcp", name="Custom MCP", group=GRP_DATA, kind="action", note="business-specific tool"),
    # The only connector with a working adapter — no external auth needed.
    _c(id="csv_import", name="CSV / JSON Import", group=GRP_DATA, kind="read", note="import companies + leads"),
]

CONNECTORS: Dict[str, Connector] = {c.id: c for c in _LIST}


def get_connector(connector_id: str) -> Connector | None:
    return CONNECTORS.get((connector_id or "").strip())


def grouped() -> List[Tuple[str, str, List[Connector]]]:
    out: List[Tuple[str, str, List[Connector]]] = []
    for g, label in GROUP_LABELS.items():
        out.append((g, label, [c for c in _LIST if c.group == g]))
    return out
