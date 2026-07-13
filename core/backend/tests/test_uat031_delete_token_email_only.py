"""Sprint 2I UAT-031 — /me/account/delete-request token must reach the
customer only via email in production. Response body never carries it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine
from app.licensing import generate_license


def _seed_license(email: str = "alice@example.com"):
    import jwt as pyjwt

    token = generate_license("cust_d31", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        existing = db.scalars(select(License).where(License.jti == jti)).first()
        if existing is None:
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


def test_delete_request_dispatches_email(client, monkeypatch):
    """The endpoint calls send_account_delete_email with the right args.

    Token must be passed to the email path, NOT to the response body in
    production. In dev/test the body still carries it for harness use.
    """
    captured: dict = {}

    def _spy(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("app.api.me_account.send_account_delete_email", _spy)

    token, jti = _seed_license()
    r = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "email_sent"
    assert body["expires_at"]

    assert captured.get("to") == "alice@example.com"
    assert captured.get("license_jti") == jti
    assert "/account/delete-confirm?token=" in captured.get("confirm_url", "")


def test_delete_request_prod_strips_token_from_response(client, monkeypatch):
    """In production the response MUST NOT carry confirm_token."""
    from app.config import settings

    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(
        "app.api.me_account.send_account_delete_email",
        lambda **_kw: None,
    )

    token, _ = _seed_license(email="bob@example.com")
    r = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "confirm_token" not in body
    assert body["status"] == "email_sent"


def test_delete_request_prod_smtp_gate(client, monkeypatch):
    """env=prod + smtp_host empty must return 503 (refuses to leak the
    flow when delivery is impossible)."""
    from app.config import settings

    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "smtp_host", "")

    token, _ = _seed_license(email="carol@example.com")
    r = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "deletion_flow_requires_smtp_in_production"


def test_dev_response_retains_token_for_test_harness(client):
    """env=dev (the default) keeps confirm_token in the body so the
    existing unit-test harness still works."""
    token, _ = _seed_license(email="dev@example.com")
    r = client.post(
        "/v1/me/account/delete-request",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "confirm_token" in body
    assert body["status"] == "email_sent"
