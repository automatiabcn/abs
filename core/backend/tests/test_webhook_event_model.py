"""WebhookEvent SQLModel schema + index + FK kontrolleri."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect

from app.db.models import WebhookEvent
from app.db.session import get_engine


def test_webhook_event_table_exists_with_expected_columns():
    """webhook_events table is created at boot + basic columns exist."""
    insp = inspect(get_engine())
    assert "webhook_events" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("webhook_events")}
    expected = {
        "event_id",
        "event_type",
        "received_at",
        "processed_at",
        "license_jti",
        "error",
    }
    missing = expected - cols
    assert not missing, f"eksik sütun(lar): {missing}"


def test_webhook_event_has_event_type_and_license_jti_indexes():
    """index defined on `event_type` + `license_jti`."""
    insp = inspect(get_engine())
    indexes = insp.get_indexes("webhook_events")
    cols = {tuple(ix["column_names"]) for ix in indexes}
    assert ("event_type",) in cols, f"event_type index yok: {indexes}"
    assert ("license_jti",) in cols, f"license_jti index yok: {indexes}"


def test_webhook_event_has_no_foreign_keys():
    """WebhookEvent.license_jti has no FK — when License is deleted, WebhookEvent remains."""
    insp = inspect(get_engine())
    fks = insp.get_foreign_keys("webhook_events")
    assert fks == [], f"beklenen FK yok ama bulundu: {fks}"

    # validate event_id PK
    pk = insp.get_pk_constraint("webhook_events")
    assert pk["constrained_columns"] == ["event_id"], pk

    # Default factory: received_at NOT NULL required (model field mandatory)
    row = WebhookEvent(event_id="test_evt_x1", event_type="test")
    assert isinstance(row.received_at, datetime)
    assert row.received_at.tzinfo == timezone.utc
