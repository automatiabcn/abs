"""Sprint 2I UAT-041 — /auth/login rate-limit + per-email backoff."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _reset_failed_logins():
    """Each test starts from a clean failed_login_attempts table so backoff
    state from a previous test does not bleed in."""
    from sqlmodel import Session, delete

    from app.db.models import FailedLoginAttempt
    from app.db.session import get_engine

    try:
        with Session(get_engine()) as db:
            db.execute(delete(FailedLoginAttempt))
            db.commit()
    except Exception:
        pass
    yield


def _wrong_login(client, email: str = "admin@local"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": "wrong"},
    )


def test_login_ip_rate_limit_5_per_minute(client):
    """slowapi @limiter.limit('5/minute') caps requests from one IP."""
    # First 5 attempts return 401 (wrong password). The 6th must be 429.
    for _ in range(5):
        r = _wrong_login(client)
        assert r.status_code == 401, r.text
    r6 = _wrong_login(client)
    assert r6.status_code == 429
    assert r6.headers.get("Retry-After")


def test_login_success_clears_failed_login_row(client, monkeypatch):
    """A successful login deletes the per-email backoff row so the next
    wrong attempt starts from zero.

    Hermetic guard: tests earlier in the run may have written a stale
    admin_credentials.json that shadows the bootstrap credentials, so
    we explicitly remove it for this test and pin the bootstrap pair.
    """
    import json
    from pathlib import Path

    from sqlmodel import Session, select

    from app.api.auth import _admin_credentials_path
    from app.config import settings
    from app.db.models import FailedLoginAttempt
    from app.db.session import get_engine

    creds_path: Path = _admin_credentials_path()
    backup: str | None = None
    if creds_path.exists():
        backup = creds_path.read_text(encoding="utf-8")
        creds_path.unlink()
    monkeypatch.setattr(settings, "admin_password_bootstrap", "CHANGEME")

    try:
        # Two wrong attempts → row exists.
        for _ in range(2):
            _wrong_login(client)
        with Session(get_engine()) as db:
            row = db.execute(
                select(FailedLoginAttempt).where(
                    FailedLoginAttempt.email == "admin@local"
                )
            ).scalars().first()
            assert row is not None
            assert row.attempts_count == 2

        r = client.post(
            "/auth/login",
            json={"email": "admin@local", "password": "CHANGEME"},
        )
        assert r.status_code == 200, r.text

        with Session(get_engine()) as db:
            row = db.execute(
                select(FailedLoginAttempt).where(
                    FailedLoginAttempt.email == "admin@local"
                )
            ).scalars().first()
            assert row is None
    finally:
        if backup is not None:
            creds_path.write_text(backup, encoding="utf-8")
        # Quiet json-unused lint when no backup is restored.
        _ = json


def test_per_email_lockout_after_threshold():
    """``_record_failed_login`` arms ``locked_until`` once the threshold
    is crossed; ``_check_locked`` returns the active deadline."""
    from app.api.auth import (
        _LOCKOUT_THRESHOLD,
        _check_locked,
        _clear_failed_login,
        _record_failed_login,
    )

    email = "lockout-test@local"
    _clear_failed_login(email)
    assert _check_locked(email) is None

    for _ in range(_LOCKOUT_THRESHOLD):
        _record_failed_login(email, None)

    locked = _check_locked(email)
    assert locked is not None
    assert locked > datetime.now(timezone.utc)
    _clear_failed_login(email)


def test_backoff_seconds_doubles_each_attempt():
    """``_backoff_seconds`` returns 0 below the threshold and doubles
    afterwards, capped at ``_LOCKOUT_MAX_SECONDS``."""
    from app.api.auth import (
        _LOCKOUT_BASE_SECONDS,
        _LOCKOUT_MAX_SECONDS,
        _LOCKOUT_THRESHOLD,
        _backoff_seconds,
    )

    assert _backoff_seconds(_LOCKOUT_THRESHOLD - 1) == 0
    assert _backoff_seconds(_LOCKOUT_THRESHOLD) == _LOCKOUT_BASE_SECONDS
    assert _backoff_seconds(_LOCKOUT_THRESHOLD + 1) == _LOCKOUT_BASE_SECONDS * 2
    assert _backoff_seconds(_LOCKOUT_THRESHOLD + 2) == _LOCKOUT_BASE_SECONDS * 4
    # Plateaus at the cap.
    assert _backoff_seconds(_LOCKOUT_THRESHOLD + 50) == _LOCKOUT_MAX_SECONDS
