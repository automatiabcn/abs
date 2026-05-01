"""T-009 — Tenant / project / tenant_projects ORM models.

Mirrors the alembic 0003_tenant_projects migration so SQLModel.metadata
recognises the tables for `init_db()` (used in tests).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True, max_length=64)
    name: str = Field(default="", max_length=128)
    created_at: datetime
    archived_at: Optional[datetime] = Field(default=None)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True, max_length=96)
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
