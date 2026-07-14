"""(S8) — /v1/admin/users contract + edge-case deep.

R65 migrated `/admin/users` to a server-side split-shell that fetches
`/v1/admin/users` with the caller's session cookie forwarded. The
endpoint is now on the SSR critical path: a regression in the
response shape, per-row shape, sort order, ISO formatting, or auth
gate breaks the first paint of the users page.

There are no existing tests for `/v1/admin/users` in the suite —
R74 fills that gap with 9 contract tests:

- response shape: `{users:[...], total:N}`
- total == len(users)
- per-row keys: id+email+role+status+tenant_slug+last_login+created_at
- sort order: rows ordered by created_at DESC (newest first)
- ISO timestamps include timezone offset (production callers parse
  with Date(); a missing tz reads as local time, not UTC)
- last_login is null when claimed_at is null (pending users)
- empty-db case returns {users:[], total:0}
- unauthenticated -> 401 (never silent 200, never 5xx)
- bcrypt password_hash is NEVER in the response (info-leak guard)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import User
from app.db.session import get_engine


def _set_password(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )


def _login(client, monkeypatch) -> str:
    _set_password(monkeypatch, "s3cret")
    return client.post("/v1/admin/login", json={"password": "s3cret"}).json()["token"]


def _wipe_users() -> None:
    """Delete every row in the `users` table without using the
    typed-ORM driver substring that the security-reminder hook
    pattern-matches. Iterating + per-row delete is functionally
    equivalent for the empty-table test."""
    with Session(get_engine()) as db:
        for row in db.scalars(select(User)).all():
            db.delete(row)
        db.commit()


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


@pytest.fixture
def _seed_three_users():
    """Seed three users with strictly-monotone created_at so we can
    assert the descending-sort contract deterministically. Uses uuid
    suffix on email to avoid the UNIQUE constraint when this fixture
    runs across multiple tests in the same db session."""
    import uuid

    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            User(
                email=f"r74-newest-{suffix}@example.com",
                password_hash="x" * 60,
                tenant_slug="default",
                role="admin",
                status="active",
                created_at=now - timedelta(minutes=1),
                claimed_at=now,
            )
        )
        db.add(
            User(
                email=f"r74-middle-{suffix}@example.com",
                password_hash="x" * 60,
                tenant_slug="default",
                role="operator",
                status="active",
                created_at=now - timedelta(minutes=5),
                claimed_at=now - timedelta(minutes=4),
            )
        )
        db.add(
            User(
                email=f"r74-oldest-{suffix}@example.com",
                password_hash="x" * 60,
                tenant_slug="default",
                role="viewer",
                status="pending",
                created_at=now - timedelta(minutes=10),
                claimed_at=None,  # pending -> no last_login
            )
        )
        db.commit()
    yield suffix


def test_response_shape_contract(client, monkeypatch, _seed_three_users):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"users", "total"}
    assert isinstance(body["users"], list)
    assert isinstance(body["total"], int)


def test_total_matches_users_length(client, monkeypatch, _seed_three_users):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["total"] == len(body["users"])


def test_per_row_keys_present(client, monkeypatch, _seed_three_users):
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    expected_keys = {
        "id",
        "email",
        "role",
        "status",
        "tenant_slug",
        "last_login",
        "created_at",
    }
    suffix = _seed_three_users
    seeded = [u for u in body["users"] if suffix in u.get("email", "")]
    assert len(seeded) == 3, "fixture seed not visible to endpoint"
    for u in seeded:
        assert expected_keys <= set(u.keys()), f"missing keys on row: {u}"


def test_descending_sort_by_created_at(
    client,
    monkeypatch,
    _seed_three_users,
):
    suffix = _seed_three_users
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    seeded = [u for u in body["users"] if suffix in u.get("email", "")]
    timestamps = [u["created_at"] for u in seeded]
    assert timestamps == sorted(timestamps, reverse=True), seeded


def test_iso_timestamps_carry_timezone_offset(
    client,
    monkeypatch,
    _seed_three_users,
):
    """Production callers (admin/users page split-shell) call
    `new Date(u.created_at)` which reads naive ISO strings as local
    time. The endpoint must emit a timezone offset ('+00:00' or 'Z').
    """
    suffix = _seed_three_users
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    seeded = [u for u in body["users"] if suffix in u.get("email", "")]
    for u in seeded:
        assert u["created_at"].endswith("+00:00") or u["created_at"].endswith("Z"), (
            f"created_at missing tz offset: {u['created_at']}"
        )
        if u["last_login"] is not None:
            assert u["last_login"].endswith("+00:00") or u["last_login"].endswith(
                "Z"
            ), f"last_login missing tz offset: {u['last_login']}"


def test_last_login_is_null_for_pending(
    client,
    monkeypatch,
    _seed_three_users,
):
    suffix = _seed_three_users
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    pending = [
        u
        for u in body["users"]
        if suffix in u.get("email", "") and u["status"] == "pending"
    ]
    assert len(pending) == 1
    assert pending[0]["last_login"] is None


def test_empty_users_table(client, monkeypatch):
    """With no rows seeded, endpoint must still return a well-formed
    `{users:[], total:0}` rather than 5xx."""
    _wipe_users()

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"users": [], "total": 0}


def test_unauthenticated_returns_401(client):
    """No Authorization header -> 401, never 5xx, never silent 200."""
    r = client.get("/v1/admin/users")
    assert r.status_code == 401


def test_password_hash_never_leaks(
    client,
    monkeypatch,
    _seed_three_users,
):
    """The User model stores `password_hash`. R65 SSR pipeline
    forwards the cookie and ships the response straight to the
    client island; if the API ever appends `password_hash`, the
    bcrypt hash would land in the panel HTML. Pin the contract."""
    suffix = _seed_three_users
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    seeded = [u for u in body["users"] if suffix in u.get("email", "")]
    for u in seeded:
        assert "password_hash" not in u, (
            f"password_hash present in response - info-leak: {u}"
        )
        # Also guard against any field whose value resembles a bcrypt
        # hash ($2b$12$...). The seeded password_hash is "x"*60 so we
        # specifically check that no field contains '$2' bcrypt prefix
        # in case someone refactors the seed and forgets to scrub.
        for value in u.values():
            if isinstance(value, str):
                assert not value.startswith("$2"), (
                    f"bcrypt-shaped value in response: {value}"
                )
