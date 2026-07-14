"""OAuth state TTL cleanup cron."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.db.models import OAuthState
from app.db.session import get_engine


def _load_cleanup():
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "oauth_state_cleanup",
        repo / "infra" / "scripts" / "oauth_state_cleanup.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["oauth_state_cleanup"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _purge_states():
    with Session(get_engine()) as s:
        for r in s.scalars(select(OAuthState)).all():
            s.delete(r)
        s.commit()


def test_cleanup_dry_run_no_delete():
    _purge_states()
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(
            OAuthState(
                state="dry_old",
                provider="github",
                redirect_url="x",
                created_at=now - timedelta(minutes=30),
            )
        )
        s.commit()

    mod = _load_cleanup()
    mod.main(["--dry-run"])

    with Session(get_engine()) as s:
        rows = s.scalars(select(OAuthState).where(OAuthState.state == "dry_old")).all()
        assert len(rows) == 1


def test_cleanup_deletes_expired_only():
    _purge_states()
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(
            OAuthState(
                state="exp_old",
                provider="github",
                redirect_url="x",
                created_at=now - timedelta(minutes=30),
            )
        )
        s.add(
            OAuthState(
                state="fresh_keep",
                provider="github",
                redirect_url="x",
                created_at=now - timedelta(minutes=2),
            )
        )
        s.commit()

    mod = _load_cleanup()
    mod.main(["--minutes", "10"])

    with Session(get_engine()) as s:
        states = {r.state for r in s.scalars(select(OAuthState)).all()}
        assert "exp_old" not in states
        assert "fresh_keep" in states


def test_state_consume_one_time(client, monkeypatch):
    """Consuming the same state twice returns 400 on the second call."""
    r1 = client.post(
        "/v1/smart-link/github/authorize",
        json={"redirect_url": "https://x"},
    )
    state = r1.json()["state"]

    # First callback succeeds (state consumed) — token exchange may fail with
    # ok=false, but state IS consumed.
    client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    # Second use → 400
    r3 = client.get(f"/v1/smart-link/github/callback?code=x&state={state}")
    assert r3.status_code == 400


def test_cleanup_idempotent_on_empty_table():
    _purge_states()
    mod = _load_cleanup()
    rc = mod.main(["--minutes", "10"])
    assert rc == 0
