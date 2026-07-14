"""Email queue tick cron entry point.

Docker compose service `abs-email-cron` runs this script every 5 minutes:
  while true; do python infra/scripts/email_tick.py; sleep 300; done

Stdout: sent=N failed=M ; exit 0 normal, 1 hata.
"""

from __future__ import annotations

import sys


def main() -> int:
    from app.email.scheduler import tick

    sent, failed = tick()
    print(f"sent={sent} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
