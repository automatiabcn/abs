# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Smart-link round — GitHub OAuth refresh must send client_id + client_secret.

GitHub's refresh_token grant REQUIRES the OAuth app credentials (exactly like
the initial code exchange). The refresh previously sent only grant_type +
refresh_token, so GitHub rejected every refresh and stored tokens silently
expired — a non-working feature. The settings fields were also never declared,
so ABS_GITHUB_CLIENT_ID / ABS_GITHUB_CLIENT_SECRET were ignored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import settings
from app.db.models import ConnectedSecret
from app.db.session import get_engine
from app.smart_link.oauth_refresh import refresh_github_token
from app.smart_link.vault_secrets import _CACHE, encrypt_secret


class _CapturingClient:
    def __init__(self, body: dict):
        self.sent_json: dict | None = None
        self._body = body

    def post(self, *a, **kw):
        self.sent_json = kw.get("json")

        class _R:
            status_code = 200

            def json(_self):
                return {
                    "access_token": "ghs_new",
                    "refresh_token": "ghr_new",
                    "expires_in": 3600,
                }

        return _R()

    def close(self):
        pass


def _seed(key: str):
    _CACHE.clear()
    encrypt_secret(key_name=key, provider="github", value="ghs_old")
    encrypt_secret(key_name=f"{key}__refresh", provider="github", value="ghr_old")
    with Session(get_engine()) as s:
        row = s.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key)
        ).first()
        row.expires_at = datetime.now(timezone.utc) + timedelta(seconds=600)
        s.add(row)
        s.commit()


def test_github_client_id_secret_are_declared_settings():
    # Declared so ABS_GITHUB_CLIENT_ID / ABS_GITHUB_CLIENT_SECRET actually load.
    assert hasattr(settings, "github_client_id")
    assert hasattr(settings, "github_client_secret")


def test_refresh_sends_client_credentials(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "Iv1.abc123", raising=False)
    monkeypatch.setattr(settings, "github_client_secret", "shh-secret", raising=False)
    _seed("creds_refresh")
    cli = _CapturingClient({})
    out = refresh_github_token(key_name="creds_refresh", http_client=cli)
    assert out["ok"] is True
    assert cli.sent_json is not None
    assert cli.sent_json.get("client_id") == "Iv1.abc123"
    assert cli.sent_json.get("client_secret") == "shh-secret"
    assert cli.sent_json.get("grant_type") == "refresh_token"
