"""/v1/admin/audit/recent pagination + cursor + cap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlmodel import Session

from app.api.admin.audit_recent import MAX_LIMIT
from app.config import settings
from app.db.models import CustomerAuditEntry
from app.db.session import get_engine


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def _seed_customer_audit(n: int) -> None:
    """Seed `n` rows so we exceed page boundaries deterministically."""
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    with Session(get_engine()) as db:
        # Clear pre-existing rows so the test is hermetic.
        for r in db.scalars(__import__("sqlmodel").select(CustomerAuditEntry)).all():
            db.delete(r)
        for i in range(n):
            db.add(
                CustomerAuditEntry(
                    license_jti=f"j{i}",
                    action="seed",
                    ts=base + timedelta(seconds=i),
                )
            )
        db.commit()


def test_default_limit_caps_at_200(client, monkeypatch):
    _seed_customer_audit(300)
    token = _admin_token(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?source=customer",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["count"] == 200
    assert body["limit"] == 200
    assert body["cursor"] is not None


def test_limit_above_max_capped_at_1000(client, monkeypatch):
    _seed_customer_audit(1200)
    token = _admin_token(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?source=customer&limit=5000",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["limit"] == MAX_LIMIT
    assert body["count"] <= MAX_LIMIT


def test_cursor_round_trip(client, monkeypatch):
    _seed_customer_audit(450)
    token = _admin_token(client, monkeypatch)
    r1 = client.get(
        "/v1/admin/audit/recent?source=customer&limit=200",
        headers={"Authorization": f"Bearer {token}"},
    )
    body1 = r1.json()
    cursor = body1["cursor"]
    assert cursor

    r2 = client.get(
        f"/v1/admin/audit/recent?source=customer&limit=200&cursor={cursor}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body2 = r2.json()
    # Page 2 must not echo any IDs from page 1.
    ids1 = {e["id"] for e in body1["entries"]}
    ids2 = {e["id"] for e in body2["entries"]}
    assert ids1.isdisjoint(ids2)
    assert body2["count"] > 0


def test_pagination_no_skip_on_identical_timestamps(client, monkeypatch):
    """3rd-eye regression — rows sharing the boundary timestamp must NOT be
    skipped. The old cursor filtered every source by ``ts < cursor_ts``, so any
    same-ts rows past the page boundary were dropped from pagination forever
    (audit-trail incompleteness). Seed 25 rows at ONE timestamp, walk with
    limit=10, and assert all 25 appear exactly once."""
    same_ts = datetime.now(timezone.utc) - timedelta(hours=3)
    with Session(get_engine()) as db:
        for r in db.scalars(__import__("sqlmodel").select(CustomerAuditEntry)).all():
            db.delete(r)
        for i in range(25):
            db.add(
                CustomerAuditEntry(license_jti=f"same{i}", action="seed", ts=same_ts)
            )
        db.commit()

    token = _admin_token(client, monkeypatch)
    seen: list[int] = []
    cursor = None
    for _ in range(12):  # bound guards against an infinite cursor loop
        url = "/v1/admin/audit/recent?source=customer&limit=10"
        if cursor:
            url += f"&cursor={cursor}"
        body = client.get(url, headers={"Authorization": f"Bearer {token}"}).json()
        seen.extend(e["id"] for e in body["entries"])
        cursor = body["cursor"]
        if not cursor:
            break

    assert len(seen) == 25, f"expected all 25 rows, saw {len(seen)} (rows skipped)"
    assert len(set(seen)) == 25, "rows duplicated across pages"


def test_invalid_cursor_returns_400(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?cursor=not-base64-and-no-pipe",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "invalid_cursor" in r.json()["detail"]
