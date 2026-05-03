"""027 Modul B — Age keypair rotation with atomic rollback.

Workflow (`rotate_age_key`):
  1. Generate new age keypair (or use injected `_keygen` for tests).
  2. Decrypt all secrets with the OLD key.
  3. Encrypt them with the NEW recipient.
  4. Atomically swap master key file (with backup).
  5. Audit-chain entry for the rotation.

If any step fails, the OLD key file is restored and the secrets file is left
untouched — guaranteeing zero data loss.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.vault import runner
from app.vault.audit_chain import append_entry

logger = logging.getLogger(__name__)


class RotationError(Exception):
    """Rotation failed; old key + secrets are intact."""


class RotationBusyError(RotationError):
    """Another rotation is currently holding the rotate lock.

    Q12-L22-002 — pre-fix two concurrent admins could each call
    `rotate_age_key`, both decrypt with the OLD recipient, both
    overwrite the master-key file (one new key clobbers the other),
    and both encrypt_all in parallel. The losing rotation's audit
    chain entry then points at a `new_fingerprint` that no longer
    matches what's actually on disk — and operators cannot tell which
    rotation 'won' without diffing the fingerprint against `age-keygen`
    output. This subclass exists so the API layer can return 409 (or
    503-busy) instead of 500.
    """


@contextlib.contextmanager
def _rotate_lock(blocking: bool = False):
    """Cross-process exclusive lock on a sibling .rotate.lock file.

    fcntl.LOCK_EX + LOCK_NB returns EWOULDBLOCK when contended; we
    raise RotationBusyError so the caller can map that to an HTTP 409
    rather than a 500. When `blocking=True` (e.g. scheduled cron) we
    wait for the holder to release.
    """
    key_path = Path(settings.vault_key_path)
    lock_path = key_path.with_suffix(key_path.suffix + ".rotate.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        op = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(fh.fileno(), op)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise RotationBusyError(
                    "another rotation is in progress"
                ) from exc
            raise
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def _fingerprint(public_recipient: str) -> str:
    return hashlib.sha256(public_recipient.encode("utf-8")).hexdigest()[:16]


def _read_recipient_from(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    raise RotationError("Master key public recipient not found")


def _default_keygen() -> str:
    """Run `age-keygen` and return key file contents."""
    if shutil.which("age-keygen") is None:
        raise RotationError("age-keygen binary not found in PATH")
    proc = subprocess.run(
        ["age-keygen"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RotationError(f"age-keygen failed: {proc.stderr[:200]}")
    return proc.stdout


def rotate_age_key(
    *,
    reason: str = "manual",
    actor: str = "admin",
    keygen: Optional[Callable[[], str]] = None,
    blocking_lock: bool = False,
) -> dict:
    """Rotate the master age key.

    Returns:
      {
        "ok": True,
        "old_fingerprint": str,
        "new_fingerprint": str,
        "secrets_re_encrypted": int,
        "elapsed_ms": float,
      }

    Raises `RotationBusyError` when another rotation already holds the
    cross-process lock and `blocking_lock=False` (default — admin API
    surface should fail fast with 409 rather than queue).
    """
    if reason not in ("manual", "scheduled", "compromise"):
        raise RotationError(f"Invalid reason: {reason}")

    with _rotate_lock(blocking=blocking_lock):
        return _rotate_age_key_locked(reason, actor, keygen)


def _rotate_age_key_locked(
    reason: str,
    actor: str,
    keygen: Optional[Callable[[], str]],
) -> dict:
    started = datetime.now(timezone.utc)
    keygen_fn = keygen or _default_keygen

    key_path = Path(settings.vault_key_path)
    if not key_path.is_file():
        raise RotationError(f"Master key file missing: {key_path}")

    old_text = key_path.read_text(encoding="utf-8")
    old_recipient = _read_recipient_from(old_text)
    old_fp = _fingerprint(old_recipient)

    # Step 1: decrypt with old key
    try:
        snapshot = runner.decrypt_all()
    except runner.VaultError as exc:
        raise RotationError(f"decrypt_all failed: {exc}") from exc

    # Step 2: generate new key (in-memory)
    new_text = keygen_fn()
    new_recipient = _read_recipient_from(new_text)
    new_fp = _fingerprint(new_recipient)

    # Step 3: write new key to a temp path, swap atomically
    backup_path = key_path.with_suffix(key_path.suffix + ".bak")
    backup_path.write_text(old_text, encoding="utf-8")
    tmp_key = Path(tempfile.mkstemp(prefix="age-new-", suffix=".key")[1])
    tmp_key.write_text(new_text, encoding="utf-8")

    try:
        # Step 4: re-encrypt secrets with the NEW key
        # We swap the key file first so encrypt_all uses the new recipient.
        shutil.move(str(tmp_key), str(key_path))
        runner.encrypt_all(snapshot)
    except Exception as exc:
        # Rollback: restore old key file from backup; secrets file is unchanged
        # (encrypt_all uses .yaml.tmp staging in runner.py).
        try:
            shutil.copy(str(backup_path), str(key_path))
        except Exception as restore_exc:
            logger.exception(
                "rotation rollback failed: %s (manual recovery required)",
                restore_exc,
            )
        raise RotationError(f"re-encrypt failed: {exc}") from exc
    finally:
        if tmp_key.exists():
            try:
                tmp_key.unlink()
            except Exception:
                pass

    # Audit
    try:
        append_entry(
            action="rotate",
            actor=actor,
            target_key="vault_master_key",
            detail=f"reason={reason} old={old_fp} new={new_fp}",
        )
    except Exception as exc:
        logger.warning("rotation audit append failed: %s", exc)

    elapsed_ms = round(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000, 2
    )
    return {
        "ok": True,
        "old_fingerprint": old_fp,
        "new_fingerprint": new_fp,
        "secrets_re_encrypted": len(snapshot),
        "elapsed_ms": elapsed_ms,
        "reason": reason,
    }
