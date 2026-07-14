"""Beta license generator (manual, repeatable).

Usage:
  python infra/scripts/generate_beta_license.py \\
      --email beta-tester@example.com \\
      --tier self-host \\
      --duration-days 180

What it does:
  1. Generate JWT (RS256) via app.licensing.generator.generate_license
  2. Insert License row in DB (customer_id_stripe='beta:<email_hash>')
  3. Send beta_invitation email (console fallback if SMTP not configured)
  4. Print LICENSE=<token> to stdout

Exit 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _setup_path() -> None:
    repo = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(repo / "core" / "backend"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a beta license JWT")
    parser.add_argument("--email", required=True, help="Beta tester email")
    parser.add_argument(
        "--tier",
        choices=["self-host", "team"],
        default="self-host",
    )
    parser.add_argument("--seat-count", type=int, default=1)
    parser.add_argument("--duration-days", type=int, default=180)
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the invitation email",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "tr", "es"],
        default="en",
        help="Email language (default: en)",
    )
    args = parser.parse_args(argv)

    _setup_path()

    from sqlmodel import Session, select

    from app.db.models import License
    from app.db.session import get_engine, init_db
    from app.licensing import generate_license, verify_license

    init_db()  # idempotent

    email_hash = hashlib.sha256(args.email.lower().encode()).hexdigest()[:16]
    customer_id = f"beta:{email_hash}"

    token = generate_license(
        customer_id=customer_id,
        tier=args.tier,
        seat_count=args.seat_count,
        valid_days=args.duration_days,
    )
    payload = verify_license(token)

    now = datetime.now(timezone.utc)
    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    with Session(get_engine()) as db:
        existing = db.scalars(
            select(License).where(License.jti == payload["jti"])
        ).first()
        if existing is None:
            db.add(
                License(
                    jti=payload["jti"],
                    customer_email=args.email,
                    customer_id_stripe=customer_id,
                    tier=args.tier,
                    seat_count=args.seat_count,
                    issued_at=issued_at,
                    expires_at=expires_at,
                    preferred_lang=args.lang,
                )
            )
            db.commit()

    if not args.no_email:
        try:
            from app.email.sender import _render, _send_html

            subject, html = _render(
                "beta_invitation.html",
                lang=args.lang,
                customer_email=args.email,
                license_key=token,
                expires_at=expires_at.strftime("%Y-%m-%d"),
                duration_days=args.duration_days,
            )
            _send_html(
                to=args.email,
                subject=subject,
                html=html,
                kind="beta_invitation",
            )
        except Exception as exc:
            print(f"WARN: email send failed: {exc}", file=sys.stderr)

    out = {
        "ok": True,
        "license_jti": payload["jti"],
        "customer_email": args.email,
        "customer_id": customer_id,
        "tier": args.tier,
        "seat_count": args.seat_count,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "lang": args.lang,
    }
    print(f"LICENSE={token}")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
