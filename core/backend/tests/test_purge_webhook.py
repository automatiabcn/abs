"""022 Modul B — Webhook purge cron."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.db.models import WebhookEvent
from app.db.session import get_engine


def _load_purge_script():
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "purge_webhook_events", repo / "infra" / "scripts" / "purge_webhook_events.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["purge_webhook_events"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _seed(event_id: str, days_ago: int, processed: bool = True):
    now = datetime.now(timezone.utc)
    row = WebhookEvent(
        event_id=event_id,
        event_type="checkout.session.completed",
        received_at=now - timedelta(days=days_ago),
        processed_at=(now - timedelta(days=days_ago - 1)) if processed else None,
    )
    with Session(get_engine()) as s:
        s.add(row)
        s.commit()


def test_purge_dry_run_no_deletes(monkeypatch):
    _seed("evt_purge_dry_old", days_ago=120)
    _seed("evt_purge_dry_new", days_ago=10)

    purge_webhook_events = _load_purge_script()

    purge_webhook_events.main(["--dry-run", "--days", "90"])

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(WebhookEvent).where(WebhookEvent.event_id.startswith("evt_purge_dry_"))
        ).all()
        assert len(rows) == 2  # dry-run silmemeli


def test_purge_real_deletes_old_keeps_orphans():
    _seed("evt_purge_real_old", days_ago=120)
    _seed("evt_purge_real_new", days_ago=10)
    _seed("evt_purge_real_orphan", days_ago=120, processed=False)

    purge_webhook_events = _load_purge_script()

    purge_webhook_events.main(["--days", "90"])

    with Session(get_engine()) as s:
        ids = {
            r.event_id
            for r in s.scalars(
                select(WebhookEvent).where(
                    WebhookEvent.event_id.startswith("evt_purge_real_")
                )
            ).all()
        }
        # old (processed) silindi
        assert "evt_purge_real_old" not in ids
        # new korundu
        assert "evt_purge_real_new" in ids
        # orphan korundu (processed_at IS NULL)
        assert "evt_purge_real_orphan" in ids
