"""028 Modul E — OAuth state TTL cleanup cron.

Deletes any OAuthState rows older than 10 minutes (or override via --minutes).

Usage:
  python infra/scripts/oauth_state_cleanup.py             # default 10 min
  python infra/scripts/oauth_state_cleanup.py --minutes 30
  python infra/scripts/oauth_state_cleanup.py --dry-run

Schedule example (cron, every 5 min):
  */5 * * * * /opt/abs/infra/scripts/oauth_state_cleanup.py >> /var/log/abs/oauth_cleanup.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OAuth state TTL purge")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from sqlmodel import select

    from app.db.models import OAuthState
    from app.db.session import get_session_sync

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.minutes)
    with get_session_sync() as db:
        rows = db.scalars(
            select(OAuthState).where(OAuthState.created_at < cutoff)
        ).all()
        candidates = len(rows)
        deleted = 0
        if not args.dry_run:
            for r in rows:
                db.delete(r)
                deleted += 1
            db.commit()

    out = {
        "cutoff": cutoff.isoformat(),
        "minutes": args.minutes,
        "candidate_count": candidates,
        "deleted": deleted,
        "dry_run": args.dry_run,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
