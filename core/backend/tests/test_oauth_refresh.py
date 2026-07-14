"""OAuth refresh token rotation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.models import ConnectedSecret
from app.db.session import get_engine
from app.smart_link.oauth_refresh import (
    _is_expired_or_close,
    refresh_github_token,
    scan_and_refresh,
)
from app.smart_link.vault_secrets import (
    _CACHE,
    decrypt_secret,
    encrypt_secret,
)


class _FakeRsp:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, rsp: _FakeRsp):
        self._rsp = rsp

    def post(self, *a, **kw):
        return self._rsp

    def close(self):
        pass


def _seed_github_secret(jti: str, expires_in: int = 3600):
    _CACHE.clear()
    encrypt_secret(key_name=jti, provider="github", value="ghs_old_access_token")
    encrypt_secret(
        key_name=f"{jti}__refresh", provider="github", value="ghr_old_refresh"
    )
    with Session(get_engine()) as s:
        row = s.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == jti)
        ).first()
        row.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        s.add(row)
        s.commit()


def test_is_expired_or_close_detects_imminent_expiry():
    secret = ConnectedSecret(
        key_name="x",
        provider="github",
        encrypted_value="b64:x",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert _is_expired_or_close(secret, lead_minutes=60) is True
    secret2 = ConnectedSecret(
        key_name="x",
        provider="github",
        encrypted_value="b64:x",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=120),
    )
    assert _is_expired_or_close(secret2, lead_minutes=60) is False


def test_refresh_no_token_returns_error():
    _CACHE.clear()
    out = refresh_github_token(key_name="missing_key")
    assert out["ok"] is False
    assert "refresh token" in out["error"].lower()


def test_refresh_success_rotates_tokens():
    _seed_github_secret("test_refresh_success")
    rsp = _FakeRsp(
        200,
        {
            "access_token": "ghs_NEW_token",
            "refresh_token": "ghr_NEW_refresh",
            "expires_in": 7200,
        },
    )
    out = refresh_github_token(
        key_name="test_refresh_success", http_client=_FakeClient(rsp)
    )
    assert out["ok"] is True
    assert out["refresh_token_rotated"] is True
    assert decrypt_secret("test_refresh_success") == "ghs_NEW_token"
    assert decrypt_secret("test_refresh_success__refresh") == "ghr_NEW_refresh"


def test_refresh_http_failure_records_error():
    _seed_github_secret("test_refresh_fail")
    rsp = _FakeRsp(401, {"error": "invalid_token"})
    out = refresh_github_token(
        key_name="test_refresh_fail", http_client=_FakeClient(rsp)
    )
    assert out["ok"] is False
    assert out["status"] == 401
    # Old token preserved (not overwritten)
    assert decrypt_secret("test_refresh_fail") == "ghs_old_access_token"


def test_refresh_emits_audit_entry():
    from app.db.models import VaultAuditEntry

    _seed_github_secret("test_audit_refresh")
    rsp = _FakeRsp(
        200,
        {"access_token": "new", "refresh_token": "new_r", "expires_in": 100},
    )
    refresh_github_token(key_name="test_audit_refresh", http_client=_FakeClient(rsp))
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(VaultAuditEntry)
            .where(VaultAuditEntry.action == "token_refresh")
            .order_by(VaultAuditEntry.id.desc())
        ).all()
        assert any(r.target_key == "test_audit_refresh" for r in rows)


def test_scan_and_refresh_only_picks_expiring(monkeypatch):
    _CACHE.clear()
    # One expiring, one fresh
    _seed_github_secret("scan_expiring", expires_in=600)  # 10 min
    _seed_github_secret("scan_fresh", expires_in=86400)  # 1 day

    captured = []

    def _fake_refresh(key_name: str, **kw):
        captured.append(key_name)
        return {"ok": True}

    monkeypatch.setattr(
        "app.smart_link.oauth_refresh.refresh_github_token",
        _fake_refresh,
    )
    out = scan_and_refresh(lead_minutes=60)
    assert "scan_expiring" in captured
    assert "scan_fresh" not in captured
    assert out["refreshed"] >= 1
    assert out["skipped"] >= 1
