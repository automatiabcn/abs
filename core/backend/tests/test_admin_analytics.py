"""032 Modul D + E + F + G — license analytics, churn, errors, audit viewer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import (
    CustomerAuditEntry,
    EmailQueue,
    License,
    VaultAuditEntry,
    WebhookEvent,
)
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


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


# ---------- D: license analytics ----------


def test_license_analytics_requires_admin(client):
    r = client.get("/v1/admin/analytics/licenses")
    assert r.status_code == 401


def test_license_analytics_returns_expected_shape(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/licenses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("cohort_granularity", "tier_breakdown", "cohorts", "expiry_calendar"):
        assert key in body
    for bucket in ("0-30d", "31-60d", "61-90d", "90d+"):
        assert bucket in body["expiry_calendar"]


def test_license_analytics_cohort_table_uses_yyyy_mm(client, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            License(
                jti="jti_cohort_test",
                customer_email="c@x.com",
                tier="self-host",
                seat_count=1,
                issued_at=now - timedelta(days=10),
                expires_at=now + timedelta(days=20),
            )
        )
        db.commit()

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/licenses",
        headers={"Authorization": f"Bearer {token}"},
    )
    cohorts = r.json()["cohorts"]
    assert len(cohorts) >= 1
    sample = cohorts[0]["cohort"]
    assert len(sample) == 7 and sample[4] == "-"


def test_license_analytics_expiry_buckets_count_correctly(client, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        # 1 license expiring in 15 days
        db.add(
            License(
                jti="jti_expiry_15",
                customer_email="e15@x.com",
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=15),
            )
        )
        db.commit()

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/licenses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["expiry_calendar"]["0-30d"] >= 1


def test_license_analytics_invalid_cohort_falls_back_to_monthly(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/licenses?cohort=garbage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["cohort_granularity"] == "monthly"


# ---------- E: churn ----------


def _seed_churn_license(jti: str, weekly_count: int, older_count: int) -> None:
    """Insert a License + audit rows so 7d-avg < 30d-avg."""
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if not db.scalars(select(License).where(License.jti == jti)).first():
            db.add(
                License(
                    jti=jti,
                    customer_email=f"{jti}@x.com",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now - timedelta(days=60),
                    expires_at=now + timedelta(days=60),
                )
            )
        for i in range(weekly_count):
            db.add(
                CustomerAuditEntry(
                    license_jti=jti,
                    action="tool_call",
                    ts=now - timedelta(days=i % 7),
                )
            )
        for i in range(older_count):
            db.add(
                CustomerAuditEntry(
                    license_jti=jti,
                    action="tool_call",
                    ts=now - timedelta(days=10 + i % 20),
                )
            )
        db.commit()


def test_churn_requires_admin(client):
    r = client.get("/v1/admin/analytics/churn")
    assert r.status_code == 401


def test_churn_flags_low_recent_usage(client, monkeypatch):
    _seed_churn_license("jti_churn_low", weekly_count=1, older_count=80)
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/churn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    flagged_ids = {f["license_jti"] for f in r.json()["flagged"]}
    assert "jti_churn_low" in flagged_ids


def test_churn_does_not_flag_steady_usage(client, monkeypatch):
    _seed_churn_license("jti_churn_steady", weekly_count=14, older_count=14)
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/analytics/churn",
        headers={"Authorization": f"Bearer {token}"},
    )
    flagged_ids = {f["license_jti"] for f in r.json()["flagged"]}
    assert "jti_churn_steady" not in flagged_ids


def test_churn_threshold_param_overrides_default(client, monkeypatch):
    _seed_churn_license("jti_churn_strict", weekly_count=4, older_count=20)
    token = _login(client, monkeypatch)
    # threshold=0 → nothing should ever flag
    r = client.get(
        "/v1/admin/analytics/churn?threshold=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["flagged_count"] == 0


# ---------- F: errors monitor ----------


def test_errors_recent_requires_admin(client):
    r = client.get("/v1/admin/errors/recent")
    assert r.status_code == 401


def test_errors_recent_combines_webhook_and_email(client, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            WebhookEvent(
                event_id="evt_err_032_1",
                event_type="invoice.paid",
                received_at=now - timedelta(hours=1),
                error="db connection lost",
            )
        )
        db.add(
            EmailQueue(
                license_jti="jti_err_email",
                customer_email="err@x.com",
                kind="welcome",
                scheduled_at=now,
                attempts=4,
                error="SMTP timeout",
            )
        )
        db.commit()

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/errors/recent",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    sources = {row["source"] for row in body["errors"]}
    assert {"webhook", "email"} <= sources


def test_errors_recent_severity_filter(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/errors/recent?severity=error",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    for row in r.json()["errors"]:
        assert row["severity"] == "error"


def test_errors_recent_invalid_severity_falls_back_to_all(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/errors/recent?severity=garbage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


# ---------- G: audit viewer ----------


def test_audit_recent_requires_admin(client):
    r = client.get("/v1/admin/audit/recent")
    assert r.status_code == 401


def test_audit_recent_combines_three_sources(client, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            VaultAuditEntry(
                action="rotate",
                actor="admin",
                target_key="age.key",
                hmac="a" * 64,
                prev_hmac="",
                ts=now - timedelta(minutes=5),
            )
        )
        db.add(
            CustomerAuditEntry(
                license_jti="jti_audit_032",
                action="tool_call",
                ts=now - timedelta(minutes=10),
            )
        )
        db.add(
            WebhookEvent(
                event_id="evt_audit_032",
                event_type="checkout.session.completed",
                received_at=now - timedelta(minutes=15),
            )
        )
        db.commit()

    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    sources = {row["source"] for row in r.json()["entries"]}
    assert {"vault", "customer", "webhook"} <= sources


def test_audit_recent_source_filter_vault_only(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?source=vault",
        headers={"Authorization": f"Bearer {token}"},
    )
    for row in r.json()["entries"]:
        assert row["source"] == "vault"


def test_audit_recent_invalid_source_falls_back_to_all(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/audit/recent?source=garbage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["source"] == "all"
