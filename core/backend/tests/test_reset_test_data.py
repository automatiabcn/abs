"""Brief 1 R4 — audit + reset_test_data regression suite.

Covers the four spec checks from
``_agent-tasks/WORKER_TEST_DATA_CLEANUP.md`` §5:

  * audit dry-run JSON schema + zero side effects
  * confirm deletes match the dry-run inventory
  * a second confirm run is a no-op (idempotent)
  * bootstrap admin / paid licences are never touched
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db.models import (
    BetaRequest,
    ChatMessage,
    ChatSession,
    CustomerAuditEntry,
    License,
    User,
)
from app.db.session import get_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_PATH = REPO_ROOT / "scripts" / "_test_data_lib.py"


def _load_lib():
    spec = importlib.util.spec_from_file_location("_test_data_lib_under_test", LIB_PATH)
    assert spec and spec.loader, "lib module not loadable"
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def _seed_test_data():
    """Seed a known mix of test + protected rows; clean up afterwards."""
    now = datetime.now(timezone.utc)

    seeded_user_emails = [
        "admin@demo-acme.com",
        "real-customer@acme.com",
        "l24scan@test.local",
        "tester-1778011095134@digisfer.local",
        "r6newadmin@digisfer.local",
        "final-1778013113205@digisfer.local",
        "chown-test-1778016011@digisfer.local",
    ]
    seeded_license_jtis = ["paid-self-host", "beta-test"]
    seeded_chat_email = "l24scan@test.local"
    seeded_beta_email = "r6newadmin@digisfer.local"

    with Session(get_engine()) as db:
        for em in seeded_user_emails:
            tenant = "demo-acme" if em == "admin@demo-acme.com" else "default"
            status = "active" if "@" in em and "test" not in em else "pending"
            db.add(
                User(
                    email=em,
                    password_hash="x",
                    tenant_slug=tenant,
                    status=status,
                )
            )
        db.add(
            License(
                jti="paid-self-host",
                customer_email="paid-customer@digisfer.local",
                tier="self-host",
                issued_at=now,
                expires_at=now,
            )
        )
        db.add(
            License(
                jti="beta-test",
                customer_email="r6newadmin@digisfer.local",
                tier="beta",
                issued_at=now,
                expires_at=now,
            )
        )
        sess = ChatSession(
            user_email=seeded_chat_email,
            tenant_slug="default",
            title="qa chat",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        db.add(ChatMessage(session_id=sess.id, role="user", content="hi"))
        db.add(ChatMessage(session_id=sess.id, role="assistant", content="hey"))
        db.add(
            BetaRequest(
                email=seeded_beta_email,
                name="qa",
                company="",
                use_case="",
            )
        )
        db.add(
            CustomerAuditEntry(
                license_jti="beta-test",
                action="login",
                resource="/api",
            )
        )
        db.commit()

    yield

    with Session(get_engine()) as db:
        for em in seeded_user_emails:
            for u in db.exec(select(User).where(User.email == em)).all():
                db.delete(u)
        for jti in seeded_license_jtis:
            for lic in db.exec(select(License).where(License.jti == jti)).all():
                db.delete(lic)
        for cs in db.exec(
            select(ChatSession).where(ChatSession.user_email == seeded_chat_email)
        ).all():
            for m in db.exec(
                select(ChatMessage).where(ChatMessage.session_id == cs.id)
            ).all():
                db.delete(m)
            db.delete(cs)
        for b in db.exec(
            select(BetaRequest).where(BetaRequest.email == seeded_beta_email)
        ).all():
            db.delete(b)
        for e in db.exec(
            select(CustomerAuditEntry).where(
                CustomerAuditEntry.license_jti == "beta-test"
            )
        ).all():
            db.delete(e)
        db.commit()


def test_audit_dry_run_schema(_seed_test_data):
    lib = _load_lib()
    report = lib.run(confirm=False, purge_rag=False)

    assert report["mode"] == "dry-run"
    assert report["purge_rag"] is False
    assert "started_at" in report and "duration_s" in report
    for cat in (
        "users",
        "chats",
        "workflows",
        "rag",
        "audits",
        "licenses",
        "beta_requests",
    ):
        assert cat in report["categories"]
        payload = report["categories"][cat]
        assert {"matched", "deleted", "samples"} <= payload.keys()
        assert payload["deleted"] == 0
    assert report["total_deleted"] == 0
    assert report["total_matched"] >= 5

    with Session(get_engine()) as db:
        all_emails = {u.email for u in db.exec(select(User)).all()}
    assert "admin@demo-acme.com" in all_emails
    assert "l24scan@test.local" in all_emails


def test_reset_confirm_counts(_seed_test_data):
    lib = _load_lib()
    dry = lib.run(confirm=False)
    confirmed = lib.run(confirm=True)

    for cat in confirmed["categories"]:
        assert (
            confirmed["categories"][cat]["deleted"] == dry["categories"][cat]["matched"]
        ), f"category {cat} deleted!=matched"

    assert confirmed["total_deleted"] == dry["total_matched"]
    assert confirmed["total_deleted"] >= 5


def test_reset_idempotent(_seed_test_data):
    lib = _load_lib()
    first = lib.run(confirm=True)
    second = lib.run(confirm=True)

    assert first["total_deleted"] >= 1
    assert second["total_deleted"] == 0
    for cat in second["categories"]:
        assert second["categories"][cat]["deleted"] == 0


def test_protected_emails_never_touched(_seed_test_data):
    lib = _load_lib()
    lib.run(confirm=True)

    with Session(get_engine()) as db:
        users_left = {u.email for u in db.exec(select(User)).all()}
        licences_left = {(lic.jti, lic.tier) for lic in db.exec(select(License)).all()}

    assert "admin@demo-acme.com" in users_left
    assert any("@acme.com" in e for e in users_left)
    assert ("paid-self-host", "self-host") in licences_left
    assert ("beta-test", "beta") not in licences_left
