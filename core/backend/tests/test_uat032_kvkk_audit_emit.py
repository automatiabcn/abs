"""An emit_event(outcome='ok') sweep across the
four KVKK success paths: delete_requested, delete_confirmed,
delete_cancelled, purge_executed."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine
from app.licensing import generate_license
from app.observability.audit import LOGGER_NAME


def _seed(email: str = "kvkk@example.com"):
    token = generate_license("kvkk-jti", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            db.add(
                License(
                    jti=jti,
                    customer_email=email,
                    customer_id_stripe="cus_x",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
            db.commit()
    return token, jti


def _audits_for(records, action: str) -> list[dict]:
    out: list[dict] = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action") == action:
            out.append(a)
    return out


def test_delete_requested_emits_ok(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
):
    monkeypatch.setattr(
        "app.api.me_account.send_account_delete_email", lambda **_kw: None
    )
    bearer, jti = _seed()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        r = client.post(
            "/v1/me/account/delete-request",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    assert r.status_code == 200
    events = _audits_for(caplog.records, "me.account.delete_requested")
    assert any(
        e.get("outcome") == "success" and e.get("user_id") == jti for e in events
    )


def test_delete_confirmed_emits_ok(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
):
    monkeypatch.setattr(
        "app.api.me_account.send_account_delete_email", lambda **_kw: None
    )
    bearer, jti = _seed()
    r1 = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    confirm_token = r1.json()["confirm_token"]
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        r = client.post(
            "/v1/me/account/delete-confirm",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"token": confirm_token},
        )
    assert r.status_code == 200
    events = _audits_for(caplog.records, "me.account.delete_confirmed")
    assert any(
        e.get("outcome") == "success" and e.get("user_id") == jti for e in events
    )


def test_delete_cancelled_emits_ok(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
):
    monkeypatch.setattr(
        "app.api.me_account.send_account_delete_email", lambda **_kw: None
    )
    bearer, jti = _seed()
    client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        r = client.post(
            "/v1/me/account/delete-cancel",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    assert r.status_code == 200
    events = _audits_for(caplog.records, "me.account.delete_cancelled")
    assert any(
        e.get("outcome") == "success" and e.get("user_id") == jti for e in events
    )


def test_purge_executed_emits_ok(
    caplog: pytest.LogCaptureFixture,
):
    """Background purge cron must emit me.account.purge_executed."""
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "uat032_purge_module",
        repo_root / "infra" / "scripts" / "purge_deleted_accounts.py",
    )
    assert spec is not None and spec.loader is not None
    purge_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(purge_module)

    _, jti = _seed(email="purge@example.com")
    # Schedule the license for purge in the past.
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        assert row is not None
        row.scheduled_delete_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.add(row)
        db.commit()

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        purge_module.main([])

    events = _audits_for(caplog.records, "me.account.purge_executed")
    assert any(
        e.get("outcome") == "success" and e.get("user_id") == jti for e in events
    )
