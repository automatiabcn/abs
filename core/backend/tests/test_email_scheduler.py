"""019 — Email scheduler: schedule, tick, retry, backoff, unsubscribe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import settings
from app.db.models import EmailQueue, License
from app.db.session import get_engine
from app.email.scheduler import (
    schedule_first_success,
    schedule_onboarding,
    tick,
    unsubscribe,
    _make_unsubscribe_token,
)


def _seed_license(jti: str, email: str = "user@x.co") -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        existing = s.scalars(select(License).where(License.jti == jti)).first()
        if existing is not None:
            return
        s.add(
            License(
                jti=jti,
                customer_email=email,
                customer_id_stripe="cus_test",
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=365),
            )
        )
        s.commit()


def _purge_queue(jti: str) -> None:
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == jti)
        ).all()
        for r in rows:
            s.delete(r)
        s.commit()


def test_schedule_onboarding_inserts_4_rows():
    _purge_queue("jti_sched_1")
    _seed_license("jti_sched_1")
    n = schedule_onboarding(license_jti="jti_sched_1", email="user@x.co")
    assert n == 4
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == "jti_sched_1")
        ).all()
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["expiry_warning", "recovery", "walkthrough", "welcome"]


def test_tick_sends_due_emails(monkeypatch):
    _purge_queue("jti_sched_due")
    _seed_license("jti_sched_due", "user-due@x.co")
    schedule_onboarding(license_jti="jti_sched_due", email="user-due@x.co")
    # Welcome row'unu yapay olarak şimdi (vakti gelmiş) yap
    with Session(get_engine()) as s:
        row = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == "jti_sched_due")
            .where(EmailQueue.kind == "welcome")
        ).first()
        assert row is not None
        row.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        s.add(row)
        s.commit()
    # SMTP host boş — console fallback (gerçek SMTP cagirilmaz)
    monkeypatch.setattr(settings, "smtp_host", "")
    sent, failed = tick()
    assert sent >= 1
    with Session(get_engine()) as s:
        row = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == "jti_sched_due")
            .where(EmailQueue.kind == "welcome")
        ).first()
        assert row.sent_at is not None


def test_tick_idempotent_skips_already_sent(monkeypatch):
    _purge_queue("jti_sched_idemp")
    _seed_license("jti_sched_idemp", "user-i@x.co")
    schedule_onboarding(license_jti="jti_sched_idemp", email="user-i@x.co")
    monkeypatch.setattr(settings, "smtp_host", "")

    # Birinci tick: welcome'i gönder
    with Session(get_engine()) as s:
        row = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == "jti_sched_idemp")
            .where(EmailQueue.kind == "welcome")
        ).first()
        row.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        s.add(row)
        s.commit()
    sent_first, _ = tick()
    assert sent_first >= 1

    # İkinci tick: aynı satır skip edilmeli (sent_at NOT NULL)
    sent_second, _ = tick()
    # Sadece bu jti'ya değil global ama bu jti'ya bakalım
    with Session(get_engine()) as s:
        sent_count = len(
            [
                r
                for r in s.scalars(
                    select(EmailQueue).where(
                        EmailQueue.license_jti == "jti_sched_idemp"
                    )
                ).all()
                if r.sent_at is not None
            ]
        )
    assert sent_count == 1  # ikinci tick aynı satırı tekrar göndermedi


def test_schedule_first_success_idempotent():
    _purge_queue("jti_sched_fs")
    _seed_license("jti_sched_fs", "user-fs@x.co")
    ok1 = schedule_first_success(license_jti="jti_sched_fs", email="user-fs@x.co")
    ok2 = schedule_first_success(license_jti="jti_sched_fs", email="user-fs@x.co")
    assert ok1 is True
    assert ok2 is False  # ikinci çağrı row eklemedi
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == "jti_sched_fs")
            .where(EmailQueue.kind == "first_success")
        ).all()
        assert len(rows) == 1


def test_unsubscribe_token_marks_rows():
    _purge_queue("jti_sched_unsub")
    _seed_license("jti_sched_unsub", "user-u@x.co")
    schedule_onboarding(license_jti="jti_sched_unsub", email="user-u@x.co")
    token = _make_unsubscribe_token("jti_sched_unsub")
    ok, info = unsubscribe(token)
    assert ok is True
    assert info == "jti_sched_unsub"
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(
                EmailQueue.license_jti == "jti_sched_unsub"
            )
        ).all()
        assert all(r.unsubscribed for r in rows)
