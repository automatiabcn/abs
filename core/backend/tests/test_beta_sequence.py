"""031 Modul B — Beta onboarding 5-stage email scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.db.models import EmailQueue
from app.db.session import get_engine
from app.email.beta_sequence import (
    BETA_STAGES,
    beta_sequence_progress,
    schedule_beta_sequence,
)


def _wipe_queue(jti: str) -> None:
    with Session(get_engine()) as db:
        for r in db.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == jti)
        ).all():
            db.delete(r)
        db.commit()


@pytest.fixture(autouse=True)
def _cleanup_beta_rows():
    """Per-test cleanup: drop every beta_* EmailQueue row.
    Without this, the 35+ beta_* rows shadow legacy seeds in unrelated tests
    that read EmailQueue with limit=50."""
    yield
    with Session(get_engine()) as db:
        for r in db.scalars(select(EmailQueue)).all():
            if r.kind and r.kind.startswith("beta_"):
                db.delete(r)
        db.commit()


def test_schedule_creates_5_rows_with_expected_kinds():
    jti = "jti_seq_01"
    _wipe_queue(jti)
    rows = schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    assert len(rows) == 5
    kinds = {r.kind for r in rows}
    assert kinds == {kind for kind, _ in BETA_STAGES}


def test_schedule_offsets_match_spec():
    jti = "jti_seq_02"
    _wipe_queue(jti)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    schedule_beta_sequence(license_jti=jti, customer_email="x@x.com", now=base)
    with Session(get_engine()) as db:
        rows = list(
            db.scalars(select(EmailQueue).where(EmailQueue.license_jti == jti)).all()
        )

    def _norm(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    by_kind = {r.kind: r for r in rows}
    assert _norm(by_kind["beta_welcome"].scheduled_at) == base
    assert _norm(by_kind["beta_walkthrough"].scheduled_at) == base + timedelta(hours=24)
    assert _norm(by_kind["beta_first_success"].scheduled_at) == base + timedelta(days=3)
    assert _norm(by_kind["beta_check_in"].scheduled_at) == base + timedelta(days=7)
    assert _norm(by_kind["beta_renewal_offer"].scheduled_at) == base + timedelta(
        days=14
    )


def test_schedule_is_idempotent():
    jti = "jti_seq_03"
    _wipe_queue(jti)
    schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    second = schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    assert second == []
    with Session(get_engine()) as db:
        count = len(
            list(
                db.scalars(
                    select(EmailQueue).where(EmailQueue.license_jti == jti)
                ).all()
            )
        )
    assert count == 5


def test_progress_reports_zero_sent_initially():
    jti = "jti_seq_04"
    _wipe_queue(jti)
    schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    progress = beta_sequence_progress(license_jti=jti)
    assert progress["scheduled"] == 5
    assert progress["sent"] == 0


def test_progress_reflects_sent_rows():
    jti = "jti_seq_05"
    _wipe_queue(jti)
    schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    with Session(get_engine()) as db:
        row = db.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == jti)
            .where(EmailQueue.kind == "beta_welcome")
        ).first()
        assert row is not None
        row.sent_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
    progress = beta_sequence_progress(license_jti=jti)
    assert progress["sent"] == 1
    assert progress["stages"]["beta_welcome"]["sent_at"] is not None


def test_unrelated_kinds_not_overcounted():
    """Existing 019 'welcome' rows must not block scheduling of 'beta_*' kinds."""
    jti = "jti_seq_06"
    _wipe_queue(jti)
    base = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            EmailQueue(
                license_jti=jti,
                customer_email="x@x.com",
                kind="welcome",
                scheduled_at=base,
            )
        )
        db.commit()
    rows = schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    assert len(rows) == 5  # all 5 beta stages still scheduled


def test_progress_counts_only_beta_kinds():
    """Non-beta rows must not inflate scheduled counter."""
    jti = "jti_seq_07"
    _wipe_queue(jti)
    base = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(
            EmailQueue(
                license_jti=jti,
                customer_email="x@x.com",
                kind="welcome",
                scheduled_at=base,
            )
        )
        db.commit()
    schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    progress = beta_sequence_progress(license_jti=jti)
    assert progress["scheduled"] == 5  # only beta_* kinds counted


def test_each_stage_has_default_attempt_zero():
    jti = "jti_seq_08"
    _wipe_queue(jti)
    rows = schedule_beta_sequence(license_jti=jti, customer_email="x@x.com")
    for r in rows:
        assert r.attempts == 0
        assert r.sent_at is None
        assert r.unsubscribed is False
