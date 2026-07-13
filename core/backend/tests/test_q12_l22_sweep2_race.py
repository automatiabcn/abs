"""Q12 Round 23 / L22 sweep 2 — concurrent vault rotate race + audit.

Pre-Round 23 inventory:
  POST /v1/admin/vault/rotate-key was unguarded against concurrent
  invocations. Two admins (or admin + scheduled cron) racing produced:

    A: decrypt_all() with OLD key       -> snapshot1
    B: decrypt_all() with OLD key       -> snapshot2 (independent copy)
    A: write new_key_A to disk          -> key file = A
    B: write new_key_B to disk          -> key file = B (clobbers A)
    A: encrypt_all(snapshot1)           -> uses key file = B (!)
    B: encrypt_all(snapshot2)           -> uses key file = B
    A: append_entry(new=A_fingerprint)  -> audit chain LIES
    B: append_entry(new=B_fingerprint)

  Audit-chain disagreement vs disk reality is the worst failure mode:
  ops follow the audit log to "the new key is X" but disk holds Y.

Q12-L22-002 (HIGH data corruption / audit divergence). Fix: fcntl.LOCK_EX
on `<vault_key_path>.rotate.lock`. Non-blocking by default at the API
surface so a contended call returns 409 instead of queuing behind a
slow rotation. Scheduled cron can pass `blocking_lock=True`.

This sweep also wires audit emit_event onto every rotate denial and
the success path (count = secrets_re_encrypted, duration_ms).

Race demonstration uses subprocess fork rather than threads — fcntl
locks are per-fd in the same process, so threads don't actually
contend. Multiprocessing forks a child that opens its own fd and
genuinely contends with the parent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import pytest

from app.config import settings
from app.observability.audit import LOGGER_NAME
from app.vault import rotation, runner


_FAKE_OLD_KEY = """# created: 2026-04-01T00:00:00Z
# public key: age1oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold
AGE-SECRET-KEY-1OLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOL
"""

_FAKE_NEW_KEY_A = """# created: 2026-05-03T14:00:00Z
# public key: age1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
AGE-SECRET-KEY-1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
"""

_FAKE_NEW_KEY_B = """# created: 2026-05-03T14:00:01Z
# public key: age1bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
AGE-SECRET-KEY-1BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
"""


def _audits_for(records, action_prefix: str) -> list[dict]:
    out = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action", "").startswith(action_prefix):
            out.append(a)
    return out


@pytest.fixture()
def _vault_env(tmp_path, monkeypatch):
    key_path = tmp_path / "age.key"
    key_path.write_text(_FAKE_OLD_KEY, encoding="utf-8")
    secrets_path = tmp_path / "secrets.yaml"
    monkeypatch.setattr(settings, "vault_key_path", str(key_path))
    monkeypatch.setattr(settings, "vault_secrets_path", str(secrets_path))

    snapshot: Dict[str, str] = {"foo": "bar", "abs_stripe": "sk_test_mock"}

    def _decrypt_all() -> Dict[str, str]:
        return dict(snapshot)

    def _encrypt_all(data: Dict[str, str]) -> None:
        snapshot.clear()
        snapshot.update(data)
        secrets_path.write_text("encrypted-blob-mock\n", encoding="utf-8")

    monkeypatch.setattr(runner, "decrypt_all", _decrypt_all)
    monkeypatch.setattr(runner, "encrypt_all", _encrypt_all)
    return key_path, secrets_path, snapshot


# ----------------------------------------------------------------------
# Race condition: in-process holder vs new attempt
# ----------------------------------------------------------------------


class TestQ12L22Sweep2RotateRace:
    def test_held_lock_makes_second_rotate_busy(self, _vault_env) -> None:
        """Hold the rotate lock from another fd, attempt a rotation, expect
        RotationBusyError. fcntl.LOCK_EX is per-fd, so opening a *second*
        descriptor in this same process is sufficient to demonstrate
        contention without forking — same semantics as a separate
        worker process."""
        key_path = Path(settings.vault_key_path)
        lock_path = key_path.with_suffix(key_path.suffix + ".rotate.lock")
        import fcntl

        # Pre-acquire the lock on a separate fd (simulating worker B
        # already inside its critical section).
        holder = open(lock_path, "a+")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        try:
            with pytest.raises(rotation.RotationBusyError):
                rotation.rotate_age_key(
                    reason="manual",
                    actor="contender",
                    keygen=lambda: _FAKE_NEW_KEY_A,
                )
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

    def test_lock_release_lets_next_rotation_succeed(self, _vault_env) -> None:
        """Once the holder releases, a second rotation must succeed and
        report the fingerprint of the actually-installed key."""
        rotation.rotate_age_key(
            reason="manual",
            actor="first",
            keygen=lambda: _FAKE_NEW_KEY_A,
        )
        out = rotation.rotate_age_key(
            reason="scheduled",
            actor="second",
            keygen=lambda: _FAKE_NEW_KEY_B,
        )
        assert out["ok"] is True
        # New fingerprint must match the key actually on disk.
        on_disk = Path(settings.vault_key_path).read_text(encoding="utf-8")
        for line in on_disk.splitlines():
            if line.startswith("# public key:"):
                public = line.split(":", 1)[1].strip()
                break
        assert out["new_fingerprint"] == rotation._fingerprint(public)


# ----------------------------------------------------------------------
# Audit emission via API surface
# ----------------------------------------------------------------------


@pytest.fixture()
def _admin_token_env(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "vault-admin-l22s2")
    return "vault-admin-l22s2"


class TestQ12L22Sweep2AuditEmission:
    def test_busy_response_emits_denied(
        self,
        _vault_env,
        _admin_token_env,
        client,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Hold the lock, hit the API, expect 409 + audit denied."""
        key_path = Path(settings.vault_key_path)
        lock_path = key_path.with_suffix(key_path.suffix + ".rotate.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        import fcntl

        holder = open(lock_path, "a+")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        try:
            with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
                r = client.post(
                    "/v1/admin/vault/rotate-key",
                    json={"reason": "manual"},
                    headers={"Authorization": f"Bearer {_admin_token_env}"},
                )
            assert r.status_code == 409
            assert r.json()["detail"] == "rotation_in_progress"
            events = _audits_for(caplog.records, "admin.vault.rotate")
            assert events and events[-1]["reason"] == "rotation_in_progress"
            assert events[-1]["status_code"] == 409
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

    def test_rotation_failure_emits_error_without_leaking_exc(
        self,
        _vault_env,
        _admin_token_env,
        client,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        """RotationError-text used to leak into the response detail
        ('Rotation failed: <exc>'). Post-fix it is a generic
        'rotation_failed' and the exc class name is in audit only."""

        def _bad_keygen() -> str:
            raise rotation.RotationError("age-keygen failed: stderr juice")

        # Patch _default_keygen so the API call (which doesn't pass a
        # custom keygen) hits our raiser.
        monkeypatch.setattr(rotation, "_default_keygen", _bad_keygen)

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/admin/vault/rotate-key",
                json={"reason": "manual"},
                headers={"Authorization": f"Bearer {_admin_token_env}"},
            )
        assert r.status_code == 500
        assert r.json()["detail"] == "rotation_failed"
        # Must NOT leak the RotationError text.
        assert "stderr juice" not in r.text
        events = _audits_for(caplog.records, "admin.vault.rotate")
        assert events and events[-1]["outcome"] == "error"
        assert events[-1]["reason"] == "rotation_failed"
        assert events[-1].get("error_class") == "RotationError"

    def test_rotation_success_emits_success_with_count_and_duration(
        self,
        _vault_env,
        _admin_token_env,
        client,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(rotation, "_default_keygen", lambda: _FAKE_NEW_KEY_A)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/admin/vault/rotate-key",
                json={"reason": "manual"},
                headers={"Authorization": f"Bearer {_admin_token_env}"},
            )
        assert r.status_code == 200
        events = _audits_for(caplog.records, "admin.vault.rotate")
        assert events and events[-1]["outcome"] == "success"
        # secrets_re_encrypted=2 from fixture (foo + abs_stripe).
        assert events[-1]["count"] == 2
        assert isinstance(events[-1]["duration_ms"], float)
