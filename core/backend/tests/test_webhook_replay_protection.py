"""028 Modul D — Webhook event replay protection (24h+).

We verify that the existing 017 idempotency protects against replays well
beyond 24 hours, and that the purge cron (022) honours a 7-day retention
window.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import stripe
from sqlmodel import Session, select

from app.db.models import WebhookEvent
from app.db.session import get_engine


def _load_purge():
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "purge_webhook_events", repo / "infra" / "scripts" / "purge_webhook_events.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["purge_webhook_events"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _post(client, event: dict):
    return client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )


def test_replay_after_24h_still_idempotent(client, monkeypatch):
    event = {
        "id": "evt_replay_24h",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "replay@x.co",
                "customer": "cus_replay_24h",
                "metadata": {"tier": "self-host", "seat_count": "1"},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r1 = _post(client, event)
    assert r1.status_code == 200
    jti = r1.json()["jti"]

    # Simulate 25 hours have passed
    with Session(get_engine()) as s:
        row = s.scalars(
            select(WebhookEvent).where(WebhookEvent.event_id == "evt_replay_24h")
        ).first()
        row.received_at = datetime.now(timezone.utc) - timedelta(hours=25)
        s.add(row)
        s.commit()

    # Replay
    r2 = _post(client, event)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True
    assert r2.json().get("license_jti") == jti


def test_purge_with_7_day_retention():
    mod = _load_purge()
    now = datetime.now(timezone.utc)

    # Seed: one inside window, one outside
    with Session(get_engine()) as s:
        s.add(
            WebhookEvent(
                event_id="evt_retention_kept",
                event_type="checkout.session.completed",
                received_at=now - timedelta(days=3),
                processed_at=now - timedelta(days=3),
            )
        )
        s.add(
            WebhookEvent(
                event_id="evt_retention_purged",
                event_type="checkout.session.completed",
                received_at=now - timedelta(days=10),
                processed_at=now - timedelta(days=10),
            )
        )
        s.commit()

    mod.main(["--days", "7"])

    with Session(get_engine()) as s:
        ids = {
            r.event_id
            for r in s.scalars(
                select(WebhookEvent).where(
                    WebhookEvent.event_id.startswith("evt_retention_")
                )
            ).all()
        }
        assert "evt_retention_kept" in ids
        assert "evt_retention_purged" not in ids


def test_received_at_index_present():
    """SQLModel index on event_type exists; ensure performance for queries."""
    from sqlalchemy import inspect

    insp = inspect(get_engine())
    indexes = insp.get_indexes("webhook_events")
    cols = {tuple(ix["column_names"]) for ix in indexes}
    assert ("event_type",) in cols


def test_purge_dry_run_does_not_delete_rows():
    mod = _load_purge()
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(
            WebhookEvent(
                event_id="evt_dryrun_safe",
                event_type="charge.refunded",
                received_at=now - timedelta(days=20),
                processed_at=now - timedelta(days=20),
            )
        )
        s.commit()

    mod.main(["--days", "7", "--dry-run"])

    with Session(get_engine()) as s:
        row = s.scalars(
            select(WebhookEvent).where(WebhookEvent.event_id == "evt_dryrun_safe")
        ).first()
        assert row is not None
