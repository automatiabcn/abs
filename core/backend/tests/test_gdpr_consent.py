"""Consent helper + endpoint tests."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.customer_audit.consent import (
    CONSENT_TYPES,
    grant_consent,
    has_consent,
    list_consents,
    withdraw_consent,
)
from app.db.session import get_engine
from app.licensing import generate_license


def _make_license_row(jti: str, email: str = "alice@example.com") -> None:
    from app.db.models import License

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if db.scalars(select(License).where(License.jti == jti)).first():
            return
        db.add(
            License(
                jti=jti,
                customer_email=email,
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now,
            )
        )
        db.commit()


def _issue_token_with_db_row(email: str = "alice@example.com") -> tuple[str, str]:
    """Generate a license JWT and ensure a matching License row exists."""
    import jwt as pyjwt

    token = generate_license("cust_test", valid_days=30)
    decoded = pyjwt.decode(token, options={"verify_signature": False})
    jti = decoded["jti"]
    _make_license_row(jti, email)
    return token, jti


def test_consent_types_set_includes_required():
    for required in {"tos", "privacy", "dpa", "marketing_email"}:
        assert required in CONSENT_TYPES


def test_grant_consent_persists():
    _, jti = _issue_token_with_db_row()
    row = grant_consent(license_jti=jti, consent_type="tos", version="1.0")
    assert row.consent_type == "tos"
    assert row.granted_at is not None
    assert row.withdrawn_at is None
    assert has_consent(license_jti=jti, consent_type="tos") is True


def test_grant_consent_idempotent_updates_version():
    _, jti = _issue_token_with_db_row()
    grant_consent(license_jti=jti, consent_type="privacy", version="1.0")
    grant_consent(license_jti=jti, consent_type="privacy", version="1.1")
    consents = list_consents(license_jti=jti)
    privacy_rows = [c for c in consents if c["consent_type"] == "privacy"]
    assert len(privacy_rows) == 1
    assert privacy_rows[0]["version"] == "1.1"


def test_withdraw_consent_marks_inactive():
    _, jti = _issue_token_with_db_row()
    grant_consent(license_jti=jti, consent_type="marketing_email")
    assert has_consent(license_jti=jti, consent_type="marketing_email") is True
    row = withdraw_consent(license_jti=jti, consent_type="marketing_email")
    assert row is not None
    assert row.withdrawn_at is not None
    assert has_consent(license_jti=jti, consent_type="marketing_email") is False


def test_consent_endpoint_grant_get_withdraw(client):
    token, jti = _issue_token_with_db_row()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/v1/me/consents",
        json={"consent_type": "tos", "version": "1.0"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["consent_type"] == "tos"

    r = client.get("/v1/me/consents", headers=headers)
    assert r.status_code == 200
    consents = r.json()["consents"]
    tos_row = [c for c in consents if c["consent_type"] == "tos"]
    assert len(tos_row) == 1
    assert tos_row[0]["active"] is True

    r = client.delete("/v1/me/consents/tos", headers=headers)
    assert r.status_code == 200
    assert r.json()["withdrawn_at"]

    r = client.get("/v1/me/consents", headers=headers)
    consents = r.json()["consents"]
    tos_row = [c for c in consents if c["consent_type"] == "tos"]
    assert tos_row[0]["active"] is False


def test_consent_endpoint_unknown_type_400(client):
    token, _ = _issue_token_with_db_row()
    r = client.post(
        "/v1/me/consents",
        json={"consent_type": "weird_unknown"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_consent_endpoint_requires_bearer(client):
    r = client.get("/v1/me/consents")
    assert r.status_code == 401
