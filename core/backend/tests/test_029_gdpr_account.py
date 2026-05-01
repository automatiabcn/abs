"""029 Modul C — Right to erasure (account deletion + purge cron)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.models import (
    Consent,
    CustomerAuditEntry,
    DataExportJob,
    EmailQueue,
    License,
)
from app.db.session import get_engine
from app.licensing import generate_license


def _make_license_row(jti: str, email: str = "alice@example.com") -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if db.scalars(select(License).where(License.jti == jti)).first():
            return
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


def _issue_token_with_db_row(email: str = "alice@example.com"):
    import jwt as pyjwt

    token = generate_license("cust_d", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    _make_license_row(jti, email)
    return token, jti


def test_delete_request_returns_token(client):
    token, _ = _issue_token_with_db_row()
    r = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["confirm_token"]
    assert body["expires_in_hours"] == 24


def test_delete_confirm_schedules_purge(client):
    token, jti = _issue_token_with_db_row()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/v1/me/account/delete-request", headers=headers)
    confirm_token = r.json()["confirm_token"]

    r = client.post(
        "/v1/me/account/delete-confirm",
        json={"token": confirm_token},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["scheduled_delete_at"]

    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        assert row.scheduled_delete_at is not None


def test_delete_confirm_rejects_other_users_token(client):
    token_a, _ = _issue_token_with_db_row(email="a@example.com")
    confirm_a = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["confirm_token"]

    token_b, _ = _issue_token_with_db_row(email="b@example.com")
    r = client.post(
        "/v1/me/account/delete-confirm",
        json={"token": confirm_a},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


def test_delete_confirm_rejects_expired_token(client):
    """An expired/invalid token must be rejected with 400."""
    token, _ = _issue_token_with_db_row()
    r = client.post(
        "/v1/me/account/delete-confirm",
        json={"token": "this.is.not.a.valid.jwt"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_delete_cancel_unschedules(client):
    token, jti = _issue_token_with_db_row()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/v1/me/account/delete-request", headers=headers)
    confirm = r.json()["confirm_token"]
    client.post(
        "/v1/me/account/delete-confirm",
        json={"token": confirm},
        headers=headers,
    )
    r = client.post("/v1/me/account/delete-cancel", headers=headers)
    assert r.status_code == 200
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        assert row.scheduled_delete_at is None


def test_purge_script_dry_run_lists_candidates():
    """Past-due license appears in dry-run output."""
    _, jti = _issue_token_with_db_row(email="purge1@example.com")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        row.scheduled_delete_at = past
        db.add(row)
        db.add(
            CustomerAuditEntry(
                license_jti=jti, action="x", ts=datetime.now(timezone.utc)
            )
        )
        db.commit()

    repo = "/Users/eneseserkan/Main/abs-server-product"
    out = subprocess.run(
        [sys.executable, f"{repo}/infra/scripts/purge_deleted_accounts.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=f"{repo}/core/backend",
    )
    assert out.returncode == 0
    assert jti in out.stdout
    assert '"dry_run": true' in out.stdout

    # dry-run must not actually purge
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        assert row.purged_at is None


def test_purge_script_executes_and_zeros_pii():
    """Past-due license PII is zeroed and child rows deleted."""
    _, jti = _issue_token_with_db_row(email="purge2@example.com")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        row.scheduled_delete_at = past
        db.add(row)
        # add some child PII rows to verify cascade-style cleanup
        db.add(
            CustomerAuditEntry(
                license_jti=jti,
                action="seen",
                ts=datetime.now(timezone.utc),
            )
        )
        db.add(
            EmailQueue(
                license_jti=jti,
                customer_email="purge2@example.com",
                kind="welcome",
                scheduled_at=datetime.now(timezone.utc),
            )
        )
        db.add(Consent(license_jti=jti, consent_type="tos"))
        db.add(
            DataExportJob(
                job_id="dxj_purge_test",
                license_jti=jti,
                customer_email="purge2@example.com",
                status="done",
            )
        )
        db.commit()

    repo = "/Users/eneseserkan/Main/abs-server-product"
    out = subprocess.run(
        [sys.executable, f"{repo}/infra/scripts/purge_deleted_accounts.py"],
        capture_output=True,
        text=True,
        cwd=f"{repo}/core/backend",
    )
    assert out.returncode == 0, out.stderr

    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        assert row is not None
        assert row.purged_at is not None
        assert row.customer_email == ""
        assert row.customer_id_stripe == ""
        # children must be gone
        assert (
            db.scalars(
                select(CustomerAuditEntry).where(
                    CustomerAuditEntry.license_jti == jti
                )
            ).first()
            is None
        )
        assert (
            db.scalars(
                select(EmailQueue).where(EmailQueue.license_jti == jti)
            ).first()
            is None
        )
        assert (
            db.scalars(select(Consent).where(Consent.license_jti == jti)).first()
            is None
        )
