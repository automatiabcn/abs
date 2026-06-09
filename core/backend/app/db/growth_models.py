# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Growth domain — canonical CRM/ERP-mirror records (SQL side).

The relational home for the Growth Context Graph entities: documents stay in
RAG, but firm/person/deal records live here (and are mirrored into Neo4j for
relationships). All tenant-scoped (RLS-enrolled in 0021). Kept deliberately
lean — enrichment/graph attributes hang off these via JSON columns + the graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Company(SQLModel, table=True):
    """Canonical firm record (entity-resolution merges into this)."""

    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    name: str = Field(max_length=256, index=True)
    vkn: Optional[str] = Field(default=None, max_length=32, index=True)  # tax id
    domain: Optional[str] = Field(default=None, max_length=128, index=True)
    sector: str = Field(default="", max_length=96)
    location: str = Field(default="", max_length=128)
    size: str = Field(default="", max_length=32)
    source: str = Field(default="", max_length=64)            # erp|crm|web|manual
    lifecycle: str = Field(default="lead", max_length=24)     # lead|opportunity|customer|partner
    score: float = Field(default=0.0)
    canonical: bool = Field(default=True)
    merged_count: int = Field(default=1)                      # source records merged
    match_confidence: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Contact(SQLModel, table=True):
    """Person at a company; consent is per-contact (Consent Ledger linkage)."""

    __tablename__ = "contacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    company_id: Optional[int] = Field(default=None, index=True)
    name: str = Field(max_length=160)
    email: Optional[str] = Field(default=None, max_length=254, index=True)
    phone: Optional[str] = Field(default=None, max_length=48)
    role: str = Field(default="", max_length=96)             # decision_maker|influencer|...
    consent_status: str = Field(default="", max_length=32)   # opt-in|opt-out|unknown
    created_at: datetime = Field(default_factory=_now)


class Lead(SQLModel, table=True):
    """A scored opportunity-to-engage tied to a company."""

    __tablename__ = "leads"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    company_id: Optional[int] = Field(default=None, index=True)
    source: str = Field(default="", max_length=64)
    intent: str = Field(default="watching", max_length=24)   # high|medium|watching
    score: float = Field(default=0.0, index=True)
    score_json: str = Field(default="{}")                    # 15-criterion breakdown
    evidence_json: str = Field(default="[]")                 # top-3 evidence
    status: str = Field(default="new", max_length=24, index=True)  # new|enriching|scored|engaged|won|lost
    owner: str = Field(default="", max_length=254)
    consent_status: str = Field(default="", max_length=32)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ConsentRecord(SQLModel, table=True):
    """Per-contact, per-channel consent + legal basis (Consent Ledger, R3).

    The product's most concrete compliance defence: an agent cannot turn a
    send-suggestion into an action unless consent allows the channel. Keyed by
    contact email within the tenant.
    """

    __tablename__ = "consent_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    contact_email: str = Field(max_length=254, index=True)
    email_consent: bool = Field(default=False)
    phone_consent: bool = Field(default=False)
    sms_consent: bool = Field(default=False)
    whatsapp_consent: bool = Field(default=False)
    do_not_call: bool = Field(default=False)
    opt_in_source: str = Field(default="", max_length=64)   # web_form|İYS|import|...
    opt_in_at: Optional[datetime] = Field(default=None)
    opt_out_at: Optional[datetime] = Field(default=None)
    legal_basis: str = Field(default="", max_length=48)     # consent|legitimate_interest
    consent_evidence: str = Field(default="", max_length=512)
    updated_at: datetime = Field(default_factory=_now)


class WorkflowRun(SQLModel, table=True):
    """An agentic workflow execution — a sequence of agent steps (P8).

    Powers the Workflow Designer run history. `steps_json` is the agent chain;
    `result_json` holds each step's structured result.
    """

    __tablename__ = "workflow_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    name: str = Field(default="", max_length=200)
    trigger: str = Field(default="manual", max_length=32)
    steps_json: str = Field(default="[]")          # ordered agent_ids
    result_json: str = Field(default="[]")         # per-step results
    status: str = Field(default="done", max_length=16, index=True)  # done|partial|error
    step_count: int = Field(default=0)
    approvals_opened: int = Field(default=0)
    elapsed_ms: int = Field(default=0)
    actor: str = Field(default="", max_length=254)
    created_at: datetime = Field(default_factory=_now, index=True)


class ConnectorState(SQLModel, table=True):
    """Per-tenant connection state for a catalog connector (Connector Layer)."""

    __tablename__ = "connector_states"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    connector_id: str = Field(max_length=48, index=True)
    status: str = Field(default="connected", max_length=16)   # connected|available|error
    health: int = Field(default=100)                          # 0..100
    connected_at: datetime = Field(default_factory=_now)
    last_sync_at: Optional[datetime] = Field(default=None)
    # Stage A — real integration: how the tenant authenticated + the encrypted
    # credential blob (Fernet, app.multitenant.crypto), the last sync outcome.
    auth_kind: str = Field(default="none", max_length=16)     # none|api_key|oauth|file
    encrypted_credentials: str = Field(default="", max_length=8192)
    last_sync_count: int = Field(default=0)
    last_error: Optional[str] = Field(default=None, max_length=512)


class AgenticWorkflowDef(SQLModel, table=True):
    """Saved Workflow Designer graph (Stage D — interactive editor).

    One canonical graph per (tenant, key). ``graph_json`` holds the node list
    (id/kind/name/desc/x/y/agent_id) plus the edge list (source/target), so the
    designer's drag-reposition, rewire and palette-add all persist. The run
    order is derived from this graph (topological over the agent nodes)."""

    __tablename__ = "agentic_workflow_defs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    key: str = Field(max_length=64, default="default", index=True)
    name: str = Field(default="", max_length=200)
    graph_json: str = Field(default="{}")           # {nodes:[...], edges:[...]}
    updated_at: datetime = Field(default_factory=_now)


class Opportunity(SQLModel, table=True):
    """A revenue opportunity (CRM/ERP-mirrored) for campaign attribution."""

    __tablename__ = "opportunities"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    company_id: Optional[int] = Field(default=None, index=True)
    name: str = Field(max_length=256)
    stage: str = Field(default="lead", max_length=32, index=True)
    amount: float = Field(default=0.0)
    currency: str = Field(default="TRY", max_length=8)
    campaign: str = Field(default="", max_length=128)        # attribution link
    created_at: datetime = Field(default_factory=_now)
