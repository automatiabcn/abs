# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-009 — Tenant / project / tenant_projects ORM models.

Mirrors the alembic 0003_tenant_projects migration so SQLModel.metadata
recognises the tables for `init_db()` (used in tests).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True, max_length=64)
    name: str = Field(default="", max_length=128)
    created_at: datetime
    archived_at: Optional[datetime] = Field(default=None)
    # Sprint 2C ITEM-1 — Settings → Genel/Marka tabs.
    branding_message: Optional[str] = Field(default=None, max_length=500)
    logo_url: Optional[str] = Field(default=None, max_length=512)
    primary_color: Optional[str] = Field(default=None, max_length=7)


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    # MT hardening: project slugs are unique PER TENANT, not globally — two
    # tenants may each have a "default" / "research" project. (Was a global
    # unique on slug, which would let tenant A's slug block tenant B.)
    __table_args__ = (
        UniqueConstraint("tenant_slug", "slug", name="uq_project_tenant_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, max_length=96)
    tenant_slug: str = Field(index=True, max_length=64)
    name: str = Field(default="", max_length=128)
    owner_subject: str = Field(default="", max_length=128)
    qdrant_collection: str = Field(default="abs_documents", max_length=128)
    created_at: datetime
    archived_at: Optional[datetime] = Field(default=None)


class TenantProject(SQLModel, table=True):
    __tablename__ = "tenant_projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(index=True, max_length=64)
    project_slug: str = Field(index=True, max_length=96)
    role: str = Field(default="member", max_length=32)
    granted_at: datetime
    revoked_at: Optional[datetime] = Field(default=None)


# ── Multi-tenant Phase 1 (data layer) ─────────────────────────────────────
# Additive tables; existing single-tenant flows are unchanged. Provider keys
# stay global (settings/vault) until the resolver is wired — these rows are an
# OPT-IN override resolved project → user → org → global.


class ProviderKey(SQLModel, table=True):
    """Per-owner (user/project/org) encrypted provider API key.

    Founder decision: each user brings their OWN key (quota/billing theirs).
    Resolution order at request time: project → user → org → global vault.
    `owner_id` is the email (user), project_slug (project), or tenant_slug (org).
    `tenant_slug` always carries the owning org so a row can be tenant-isolated.
    `encrypted_value` is a versioned ciphertext (see app.multitenant.crypto).
    """

    __tablename__ = "provider_keys"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(index=True, max_length=64)
    owner_type: str = Field(index=True, max_length=16)  # user | project | org
    owner_id: str = Field(index=True, max_length=128)
    provider: str = Field(index=True, max_length=32)
    encrypted_value: str = Field(max_length=8192)
    created_at: datetime
    updated_at: Optional[datetime] = Field(default=None)
    last_validated_at: Optional[datetime] = Field(default=None)
    last_validated_ok: Optional[bool] = Field(default=None)


class TenantSetting(SQLModel, table=True):
    """Generic per-tenant settings sections (webhooks / alerts / security / …).

    Backs the /admin/settings tabs that previously had dead Save buttons. One
    row per (tenant_slug, section); ``data_json`` holds the section's fields.
    Kept generic so a new settings section needs no schema change.
    """

    __tablename__ = "tenant_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(index=True, max_length=64)
    section: str = Field(index=True, max_length=48)
    data_json: str = Field(default="{}")
    updated_at: datetime
    updated_by: str = Field(default="", max_length=254)


class ProjectMember(SQLModel, table=True):
    """N-N user↔project membership with a per-project role.

    Distinct from `tenant_projects` (tenant↔project sharing). A user may belong
    to MULTIPLE projects (founder decision); the active project is selected per
    request. Roles: owner | editor | viewer.
    """

    __tablename__ = "project_members"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(index=True, max_length=64)
    project_slug: str = Field(index=True, max_length=96)
    user_subject: str = Field(index=True, max_length=128)
    role: str = Field(default="viewer", max_length=32)
    granted_at: datetime
    revoked_at: Optional[datetime] = Field(default=None)


# ── External MCP federation (ABS as MCP *client*) ─────────────────────────
# Founder direction (2026-06-08): a tenant adds a third-party MCP server
# (GitHub / Slack / their own) from the panel; ABS connects to it as a client,
# discovers its tools and (Slice 2) federates them into its own catalog +
# agents. Credentials are Fernet-encrypted (app.multitenant.crypto); the
# plaintext auth value is NEVER returned by the API. Tenant-scoped + RLS so one
# tenant cannot see another's servers.


class ExternalMcpServer(SQLModel, table=True):
    """A third-party MCP server registered by a tenant for tool federation."""

    __tablename__ = "external_mcp_servers"
    __table_args__ = (
        UniqueConstraint("tenant_slug", "slug", name="uq_external_mcp_tenant_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(index=True, max_length=64)
    slug: str = Field(index=True, max_length=64)          # stable id within tenant
    name: str = Field(default="", max_length=128)         # human label
    url: str = Field(max_length=2048)                      # transport endpoint
    transport: str = Field(default="http", max_length=16)  # http | sse
    auth_type: str = Field(default="none", max_length=16)  # none | bearer | header
    # Fernet ciphertext of the bearer token / header value (empty when none).
    encrypted_auth: str = Field(default="", max_length=8192)
    header_name: str = Field(default="", max_length=64)    # for auth_type=header
    enabled: bool = Field(default=True)
    # Discovery / health snapshot from the last test_connection.
    status: str = Field(default="unconfigured", max_length=24)  # ok|error|unconfigured
    last_error: Optional[str] = Field(default=None, max_length=512)
    discovered_tool_count: int = Field(default=0)
    last_checked_at: Optional[datetime] = Field(default=None)
    created_at: datetime
    created_by: str = Field(default="", max_length=254)
    updated_at: Optional[datetime] = Field(default=None)
