"""Demo seed: realistic but synthetic sample data.

Usage:
  python infra/scripts/seed_demo_data.py [--reset]

Idempotent: writes a versioned marker (`demo_seed_v<N>`) into a new
`SeedMarker`-style state file at $ABS_DATA_DIR/demo_seed_state.json. If
that file matches the current SEED_VERSION, the script exits 0 with no
changes unless `--reset` is passed.

Generates:
  - 5 sample licenses (mixed tiers)
  - 20 webhook events (checkout/refund/ignored)
  - 50 customer audit log entries
  - 15 wizard events (funnel with drop-off)
  - 8 beta requests (3 approved, 5 pending)
  - 30 vault audit entries
  - 3 connected secrets (encrypted dummy)

Output JSON to stdout summarises what was written. Path conventions assume
the script is invoked from `core/backend/` so settings.data_dir resolves
correctly.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED_VERSION = "v1"


def _now_minus(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        days=days, hours=hours, minutes=minutes
    )


def _state_path() -> Path:
    from app.config import settings

    return Path(settings.data_dir) / "demo_seed_state.json"


def _check_idempotent(force_reset: bool) -> bool:
    """Return True if seeding should proceed."""
    p = _state_path()
    if force_reset:
        return True
    if not p.exists():
        return True
    try:
        data = json.loads(p.read_text())
    except Exception:
        return True
    return data.get("seed_version") != SEED_VERSION


def _wipe_existing(db) -> None:
    """Drop only rows tagged with the demo prefix so real data is safe."""
    from sqlmodel import select

    from app.db.models import (
        BetaRequest,
        ConnectedSecret,
        CustomerAuditEntry,
        License,
        VaultAuditEntry,
        WebhookEvent,
        WizardEvent,
    )

    for r in db.scalars(select(License)).all():
        if (r.customer_id_stripe or "").startswith("demo:"):
            db.delete(r)
    for r in db.scalars(select(WebhookEvent)).all():
        if (r.event_id or "").startswith("demo_"):
            db.delete(r)
    for r in db.scalars(select(CustomerAuditEntry)).all():
        if (r.license_jti or "").startswith("demo_jti_"):
            db.delete(r)
    for r in db.scalars(select(WizardEvent)).all():
        if (r.session_id or "").startswith("demo_sess_"):
            db.delete(r)
    for r in db.scalars(select(BetaRequest)).all():
        if r.email and r.email.endswith("@meetingco.test"):
            db.delete(r)
    for r in db.scalars(select(VaultAuditEntry)).all():
        if (r.target_key or "").startswith("demo:"):
            db.delete(r)
    for r in db.scalars(select(ConnectedSecret)).all():
        if (r.key_name or "").startswith("demo_"):
            db.delete(r)
    db.commit()


def _seed_licenses(db) -> list[str]:
    from app.db.models import License

    licenses_def = [
        ("self-host", 1),
        ("team", 5),
        ("team", 10),
        ("self-host", 1),
        ("beta", 1),
    ]
    jtis = []
    for i, (tier, seats) in enumerate(licenses_def):
        jti = f"demo_jti_{i}_{uuid.uuid4().hex[:12]}"
        jtis.append(jti)
        issued = _now_minus(days=30 + i * 12)
        db.add(
            License(
                jti=jti,
                customer_email=f"demo+{i}@meetingco.test",
                customer_id_stripe=f"demo:cus_{i:04d}",
                tier=tier,
                seat_count=seats,
                issued_at=issued,
                expires_at=issued + timedelta(days=365),
                preferred_lang=["en", "tr", "es", "en", "en"][i],
            )
        )
    db.commit()
    return jtis


def _seed_webhook_events(db) -> int:
    from app.db.models import WebhookEvent

    rows = []
    types = ["checkout.session.completed"] * 5 + [
        "charge.refunded"
    ] * 2 + ["customer.subscription.updated"] * 13
    for i, evt_type in enumerate(types):
        rows.append(
            WebhookEvent(
                event_id=f"demo_evt_{i:03d}",
                event_type=evt_type,
                received_at=_now_minus(hours=24 - i),
                processed_at=_now_minus(hours=24 - i, minutes=-5),
                license_jti=None,
                error=None if evt_type != "charge.refunded" else None,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


def _seed_customer_audit(db, jtis: list[str]) -> int:
    from app.db.models import CustomerAuditEntry

    actions = [
        "login",
        "license_activate",
        "tool_call",
        "key_added",
        "consent.granted",
        "data_export.requested",
    ]
    rows = []
    for i in range(50):
        rows.append(
            CustomerAuditEntry(
                license_jti=jtis[i % len(jtis)],
                action=actions[i % len(actions)],
                resource=f"resource_{i % 7}",
                ts=_now_minus(hours=i),
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


def _seed_wizard_events(db) -> int:
    from app.db.models import WizardEvent

    rows = []
    for sess in range(3):
        # 6-step funnel; one session drops at step 4
        max_step = 6 if sess < 2 else 4
        for step in range(max_step):
            started = _now_minus(days=sess + 1, minutes=step * 3)
            rows.append(
                WizardEvent(
                    session_id=f"demo_sess_{sess}",
                    step_num=step,
                    started_at=started,
                    completed_at=started + timedelta(minutes=2),
                )
            )
    # Pad to 15
    while len(rows) < 15:
        rows.append(
            WizardEvent(
                session_id=f"demo_sess_pad_{len(rows)}",
                step_num=0,
                started_at=_now_minus(days=10),
            )
        )
    db.add_all(rows[:15])
    db.commit()
    return len(rows[:15])


def _seed_beta_requests(db) -> int:
    from app.db.models import BetaRequest

    rows = []
    for i in range(8):
        is_approved = i < 3
        rows.append(
            BetaRequest(
                email=f"prospect{i}@meetingco.test",
                name=["Alice", "Bob", "Carol", "Dan", "Eve", "Faye", "Greg", "Hana"][i],
                company=f"Co{i}",
                use_case="Internal coding agent",
                lang=["en", "tr", "es"][i % 3],
                status="approved" if is_approved else "pending",
                created_at=_now_minus(days=i),
                approved_at=_now_minus(days=i, hours=-1) if is_approved else None,
                license_jti=None,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


def _seed_vault_audit(db) -> int:
    from app.db.models import VaultAuditEntry

    rows = []
    prev = ""
    for i in range(30):
        h = secrets.token_hex(32)
        rows.append(
            VaultAuditEntry(
                action=["encrypt", "decrypt", "rotate"][i % 3],
                actor="demo",
                target_key=f"demo:secret_{i % 5}",
                hmac=h,
                prev_hmac=prev,
                ts=_now_minus(hours=i * 2),
            )
        )
        prev = h
    db.add_all(rows)
    db.commit()
    return len(rows)


def _seed_connected_secrets(db) -> int:
    from app.db.models import ConnectedSecret

    rows = [
        ConnectedSecret(
            key_name=f"demo_{name}",
            provider=name,
            encrypted_value=f"demo_encrypted_{name}",
            last_validated_ok=True,
        )
        for name in ("github", "slack", "openai")
    ]
    db.add_all(rows)
    db.commit()
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ABS demo data seeder")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)

    from sqlmodel import Session

    from app.db.session import get_engine

    if not _check_idempotent(args.reset):
        out = {
            "skipped": True,
            "reason": "seed_version_match",
            "seed_version": SEED_VERSION,
        }
        print(json.dumps(out, indent=2))
        return 0

    summary: dict = {"seed_version": SEED_VERSION, "counts": {}}
    with Session(get_engine()) as db:
        if args.reset:
            _wipe_existing(db)
        jtis = _seed_licenses(db)
        summary["counts"]["licenses"] = len(jtis)
        summary["counts"]["webhook_events"] = _seed_webhook_events(db)
        summary["counts"]["customer_audit"] = _seed_customer_audit(db, jtis)
        summary["counts"]["wizard_events"] = _seed_wizard_events(db)
        summary["counts"]["beta_requests"] = _seed_beta_requests(db)
        summary["counts"]["vault_audit"] = _seed_vault_audit(db)
        summary["counts"]["connected_secrets"] = _seed_connected_secrets(db)

    state_path = _state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "seed_version": SEED_VERSION,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
                "counts": summary["counts"],
            },
            indent=2,
        )
    )
    summary["state_path"] = str(state_path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
