"""022 — WebhookEvent purge cron — 90 gün öncesini sil.

Cron senaryosu (haftalık):
  python infra/scripts/purge_webhook_events.py [--dry-run] [--days N]

Davranış:
- `processed_at IS NOT NULL` (orphan'ları tut, manuel inceleme için).
- `received_at < now - N days` filtre (default 90).
- `--dry-run` sadece sayar, silmez.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WebhookEvent purge cron")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args(argv)

    from sqlmodel import select

    from app.db.models import WebhookEvent
    from app.db.session import get_session_sync

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    with get_session_sync() as db:
        rows = db.scalars(
            select(WebhookEvent)
            .where(WebhookEvent.received_at < cutoff)
            .where(WebhookEvent.processed_at.is_not(None))  # type: ignore[union-attr]
        ).all()

        out = {
            "cutoff": cutoff.isoformat(),
            "candidate_count": len(rows),
            "dry_run": args.dry_run,
            "deleted": 0,
        }
        if not args.dry_run:
            for r in rows:
                db.delete(r)
            db.commit()
            out["deleted"] = len(rows)

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
