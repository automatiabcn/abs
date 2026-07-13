"""019 — first_success trigger: ilk MCP tool çağrısında email scheduled, sonraki çağrılarda değil."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import settings
from app.db.models import EmailQueue, License
from app.db.session import get_engine
from app.licensing import generate_license


def _seed_license_and_settings(monkeypatch):
    token = generate_license(customer_id="cus_fs_test", tier="self-host", seat_count=1)
    from app.licensing import verify_license

    payload = verify_license(token)
    jti = payload["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        existing = s.scalars(select(License).where(License.jti == jti)).first()
        if existing is None:
            s.add(
                License(
                    jti=jti,
                    customer_email="fs-trig@x.co",
                    customer_id_stripe="cus_fs_test",
                    tier="self-host",
                    seat_count=1,
                    issued_at=now,
                    expires_at=now + timedelta(days=365),
                )
            )
            s.commit()
    monkeypatch.setattr(settings, "license_key", token)
    return jti


def _purge_first_success(jti: str):
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == jti)
            .where(EmailQueue.kind == "first_success")
        ).all()
        for r in rows:
            s.delete(r)
        # License.first_tool_call_at reset
        lic = s.scalars(select(License).where(License.jti == jti)).first()
        if lic:
            lic.first_tool_call_at = None
            s.add(lic)
        s.commit()


def test_first_mcp_call_triggers_first_success(monkeypatch):
    jti = _seed_license_and_settings(monkeypatch)
    _purge_first_success(jti)

    from app.mcp.middleware import _maybe_trigger_first_success

    _maybe_trigger_first_success("system_status")

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == jti)
            .where(EmailQueue.kind == "first_success")
        ).all()
        assert len(rows) == 1

        lic = s.scalars(select(License).where(License.jti == jti)).first()
        assert lic.first_tool_call_at is not None


def test_subsequent_calls_do_not_trigger(monkeypatch):
    jti = _seed_license_and_settings(monkeypatch)
    _purge_first_success(jti)

    from app.mcp.middleware import _maybe_trigger_first_success

    _maybe_trigger_first_success("system_status")
    _maybe_trigger_first_success("ask_groq_fast")
    _maybe_trigger_first_success("rag_query")

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue)
            .where(EmailQueue.license_jti == jti)
            .where(EmailQueue.kind == "first_success")
        ).all()
        # İlk çağrı 1 row schedule etti, sonrakiler no-op
        assert len(rows) == 1
