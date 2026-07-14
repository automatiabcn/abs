# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Alembic 0012 migration smoke tests."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa


_MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0012_tenant_settings_and_fk_cascades.py"
)


def test_migration_file_exists():
    assert _MIGRATION_FILE.is_file()


def test_branding_columns_present_on_tenants_table():
    from app.db.session import get_engine

    engine = get_engine()
    inspector = sa.inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("tenants")}
    assert "branding_message" in cols
    assert "logo_url" in cols
    assert "primary_color" in cols


def test_migration_documents_lesson_9_followup():
    text = _MIGRATION_FILE.read_text(encoding="utf-8")
    assert "Lesson 9" in text or "FK CASCADE" in text or "deferred" in text.lower()


def test_tenant_model_exposes_new_attrs():
    from app.db.tenant_models import Tenant

    fields = Tenant.model_fields
    assert "branding_message" in fields
    assert "logo_url" in fields
    assert "primary_color" in fields
