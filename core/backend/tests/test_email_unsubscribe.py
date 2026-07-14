"""Unsubscribe endpoint: token verify + DB update."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.models import EmailQueue
from app.db.session import get_engine
from app.email.scheduler import _make_unsubscribe_token


def _seed_queue(jti: str, email: str = "u-test@x.co"):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        for kind in ("welcome", "walkthrough"):
            s.add(
                EmailQueue(
                    license_jti=jti,
                    customer_email=email,
                    kind=kind,
                    scheduled_at=now + timedelta(hours=1),
                )
            )
        s.commit()


def test_unsubscribe_endpoint_marks_rows(client):
    _seed_queue("jti_unsub_ep")
    token = _make_unsubscribe_token("jti_unsub_ep")
    r = client.get(f"/v1/email/unsubscribe?token={token}")
    assert r.status_code == 200
    assert "You have been unsubscribed" in r.text

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == "jti_unsub_ep")
        ).all()
        assert all(r.unsubscribed for r in rows)
