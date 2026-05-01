"""027 Modul B — Age key rotation (mocked age-keygen + sops)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from app.config import settings
from app.vault import rotation, runner


_FAKE_OLD_KEY = """# created: 2026-04-01T00:00:00Z
# public key: age1oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold
AGE-SECRET-KEY-1OLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOL
"""

_FAKE_NEW_KEY = """# created: 2026-04-27T13:00:00Z
# public key: age1newnewnewnewnewnewnewnewnewnewnewnewnewnewnewnew
AGE-SECRET-KEY-1NEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEW
"""


@pytest.fixture()
def _vault_env(tmp_path, monkeypatch):
    """Isolate vault paths to tmp + fake decrypt/encrypt."""
    key_path = tmp_path / "age.key"
    key_path.write_text(_FAKE_OLD_KEY, encoding="utf-8")
    secrets_path = tmp_path / "secrets.yaml"
    monkeypatch.setattr(settings, "vault_key_path", str(key_path))
    monkeypatch.setattr(settings, "vault_secrets_path", str(secrets_path))

    snapshot: Dict[str, str] = {}

    def _decrypt_all() -> Dict[str, str]:
        return dict(snapshot)

    def _encrypt_all(data: Dict[str, str]) -> None:
        snapshot.clear()
        snapshot.update(data)
        secrets_path.write_text("encrypted-blob-mock\n", encoding="utf-8")

    monkeypatch.setattr(runner, "decrypt_all", _decrypt_all)
    monkeypatch.setattr(runner, "encrypt_all", _encrypt_all)

    snapshot["foo"] = "bar"
    snapshot["abs_stripe"] = "sk_test_mock"
    return key_path, secrets_path, snapshot


def test_rotate_happy_path(_vault_env):
    key_path, _secrets, _snap = _vault_env
    out = rotation.rotate_age_key(
        reason="scheduled",
        actor="test",
        keygen=lambda: _FAKE_NEW_KEY,
    )
    assert out["ok"] is True
    assert out["secrets_re_encrypted"] == 2
    assert out["old_fingerprint"] != out["new_fingerprint"]
    # Master key file replaced
    assert "age1newnewnewnew" in key_path.read_text()


def test_rotate_invalid_reason_raises(_vault_env):
    with pytest.raises(rotation.RotationError, match="Invalid reason"):
        rotation.rotate_age_key(reason="bogus", keygen=lambda: _FAKE_NEW_KEY)


def test_rotate_decrypt_fail_rolls_back(_vault_env, monkeypatch):
    key_path, _secrets, _snap = _vault_env

    def _decrypt_fail() -> Dict[str, str]:
        raise runner.VaultError("simulated decrypt fail")

    monkeypatch.setattr(runner, "decrypt_all", _decrypt_fail)

    with pytest.raises(rotation.RotationError, match="decrypt_all failed"):
        rotation.rotate_age_key(keygen=lambda: _FAKE_NEW_KEY)
    # Old key still in place
    assert "age1oldoldold" in key_path.read_text()


def test_rotate_encrypt_fail_restores_old_key(_vault_env, monkeypatch):
    key_path, _secrets, _snap = _vault_env

    def _encrypt_fail(data):
        raise runner.VaultError("simulated encrypt fail")

    monkeypatch.setattr(runner, "encrypt_all", _encrypt_fail)

    with pytest.raises(rotation.RotationError, match="re-encrypt failed"):
        rotation.rotate_age_key(keygen=lambda: _FAKE_NEW_KEY)
    # Atomic rollback: old key restored
    assert "age1oldoldold" in key_path.read_text()


def test_fingerprint_stable_for_same_recipient():
    fp1 = rotation._fingerprint("age1abcdef")
    fp2 = rotation._fingerprint("age1abcdef")
    fp3 = rotation._fingerprint("age1xyz")
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 16


def test_rotation_emits_audit_entry(_vault_env):
    from sqlmodel import Session, select

    from app.db.models import VaultAuditEntry
    from app.db.session import get_engine

    # Snapshot count before
    with Session(get_engine()) as s:
        before = len(s.scalars(select(VaultAuditEntry)).all())

    rotation.rotate_age_key(
        reason="manual", actor="test-actor", keygen=lambda: _FAKE_NEW_KEY
    )

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(VaultAuditEntry).order_by(VaultAuditEntry.id.desc())
        ).all()
        assert len(rows) > before
        latest = rows[0]
        assert latest.action == "rotate"
        assert latest.actor == "test-actor"
        assert "reason=manual" in (latest.detail or "")


# ---- Endpoint tests ----------------------------------------------------------


def test_endpoint_requires_bearer(client):
    r = client.post("/v1/admin/vault/rotate-key", json={"reason": "manual"})
    assert r.status_code == 401


def test_endpoint_wrong_token_returns_403(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-vault-admin-027")
    r = client.post(
        "/v1/admin/vault/rotate-key",
        json={"reason": "manual"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 403


def test_endpoint_runs_rotation(client, monkeypatch, _vault_env):
    monkeypatch.setattr(settings, "admin_token", "test-vault-admin-027")
    monkeypatch.setattr(rotation, "_default_keygen", lambda: _FAKE_NEW_KEY)

    r = client.post(
        "/v1/admin/vault/rotate-key",
        json={"reason": "scheduled"},
        headers={"Authorization": "Bearer test-vault-admin-027"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["reason"] == "scheduled"
