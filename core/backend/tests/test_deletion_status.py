"""GET /v1/me/account/deletion-status surfaces the
30-day grace window to the panel UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine
from app.licensing import generate_license


def _seed(scheduled_in_days: int | None = None, purged: bool = False):
    token = generate_license("uat038-jti", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            row = License(
                jti=jti,
                customer_email="x@example.com",
                customer_id_stripe="cus_x",
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=30),
            )
        if scheduled_in_days is not None:
            row.scheduled_delete_at = now + timedelta(days=scheduled_in_days)
        else:
            row.scheduled_delete_at = None
        row.purged_at = now if purged else None
        db.add(row)
        db.commit()
    return token


def test_deletion_status_none(client):
    token = _seed()
    r = client.get(
        "/v1/me/account/deletion-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "none"
    assert body["days_remaining"] == 0


def test_deletion_status_scheduled(client):
    token = _seed(scheduled_in_days=12)
    r = client.get(
        "/v1/me/account/deletion-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["status"] == "scheduled"
    assert 10 <= body["days_remaining"] <= 12
    assert body["scheduled_delete_at"]


def test_deletion_status_purged(client):
    token = _seed(purged=True)
    r = client.get(
        "/v1/me/account/deletion-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["status"] == "purged"
    assert body["purged_at"]
