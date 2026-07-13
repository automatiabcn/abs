# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""sops + age subprocess wrapper.

Shell commands:
  sops -d <path>            → stdout: plaintext yaml
  sops -e -i ... <path>     → in-place encrypt
  age-keygen -o <key_path>  → yeni master key (manuel: init_vault.sh)

Master key dosya yolu: settings.vault_key_path (default /app/vault-key/age.key)
Secrets file:       settings.vault_secrets_path (default /app/data/secrets.yaml)

Cleartext disk'te kalmasin: sops -d stdout'a, dosyaya yazmiyor.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """A vault operation failed — transient or not."""

    def __init__(self, msg: str, *, transient: bool = False):
        super().__init__(msg)
        self.transient = transient


def sops_available() -> bool:
    return shutil.which("sops") is not None and shutil.which("age") is not None


def sops_version() -> Optional[str]:
    """Return sops version string (e.g. '3.7.3') or None if not installed."""
    if shutil.which("sops") is None:
        return None
    try:
        result = subprocess.run(
            ["sops", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Output: "sops 3.7.3 (latest)\n..."
        first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
        parts = first_line.split()
        if len(parts) >= 2:
            return parts[1]
    except Exception:
        return None
    return None


def _version_at_least(actual: str, required: str) -> bool:
    """Compare semver-ish strings: '3.7.3' >= '3.7.0'."""

    def _parse(v: str) -> tuple:
        return tuple(int(p) for p in v.split(".")[:3] if p.isdigit())

    try:
        return _parse(actual) >= _parse(required)
    except Exception:
        return False


def check_production_vault() -> None:
    """Boot-time check: if `vault_require_sops` set, fail-fast on missing/old sops.

    Dev mode (`vault_require_sops=False`): warn log only, no exception.
    """
    if not settings.vault_require_sops:
        if not sops_available():
            logger.warning(
                "vault: sops/age not installed — running in dev fallback mode "
                "(set ABS_VAULT_REQUIRE_SOPS=true to enforce in production)"
            )
        return
    if not sops_available():
        raise RuntimeError(
            "ABS_VAULT_REQUIRE_SOPS=true but sops/age binary not found in PATH. "
            "Install: https://github.com/getsops/sops/releases (>= "
            f"{settings.vault_min_sops_version})"
        )
    version = sops_version()
    if version is None:
        raise RuntimeError("sops binary found but `sops --version` produced no output.")
    if not _version_at_least(version, settings.vault_min_sops_version):
        raise RuntimeError(
            f"sops version {version} < required {settings.vault_min_sops_version}"
        )
    logger.info("vault: sops %s detected (production mode)", version)


def master_key_exists() -> bool:
    return Path(settings.vault_key_path).is_file()


def _sops_env() -> Dict[str, str]:
    """Subprocess'a SOPS_AGE_KEY_FILE inject et."""
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = settings.vault_key_path
    return env


def decrypt_all() -> Dict[str, Any]:
    """Decrypt secrets.yaml into a dict. Missing file yields an empty dict."""
    if not sops_available():
        raise VaultError("sops/age is not installed", transient=False)
    if not master_key_exists():
        raise VaultError(
            f"Master key not found: {settings.vault_key_path}",
            transient=False,
        )
    secrets_path = Path(settings.vault_secrets_path)
    if not secrets_path.is_file():
        return {}  # empty vault — fresh install
    try:
        result = subprocess.run(
            [
                "sops",
                "-d",
                "--input-type",
                "yaml",
                "--output-type",
                "yaml",
                str(secrets_path),
            ],
            env=_sops_env(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise VaultError(
            f"sops decrypt fail: {(exc.stderr or '')[:200]}", transient=False
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultError("sops decrypt timeout", transient=True) from exc
    try:
        parsed = yaml.safe_load(result.stdout) or {}
        if not isinstance(parsed, dict):
            raise VaultError("vault yaml must be a JSON object", transient=False)
        # Backward-compat: a vault written by the pre-fix code (sops binary mode
        # via the ".yaml.tmp" extension) wraps the whole document under a single
        # `data:` string. Unwrap it so an upgraded install recovers its old
        # secrets immediately, without needing the operator to re-enter keys.
        if set(parsed.keys()) == {"data"} and isinstance(parsed["data"], str):
            inner = yaml.safe_load(parsed["data"]) or {}
            if isinstance(inner, dict):
                return inner
        return parsed
    except yaml.YAMLError as exc:
        raise VaultError(f"yaml parse fail: {exc}", transient=False) from exc


def _read_age_recipient() -> str:
    """Master key dosyasindan public recipient'i cikar (age-keygen formati)."""
    p = Path(settings.vault_key_path)
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    raise VaultError("Master key has no public recipient", transient=False)


def encrypt_all(data: Dict[str, Any]) -> None:
    """Encrypt the whole dict and write secrets.yaml in place, atomically."""
    if not sops_available():
        raise VaultError("sops/age is not installed", transient=False)
    if not master_key_exists():
        raise VaultError(
            f"Master key not found: {settings.vault_key_path}",
            transient=False,
        )
    secrets_path = Path(settings.vault_secrets_path)
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    age_recipient = _read_age_recipient()
    plain_yaml = yaml.safe_dump(data, allow_unicode=True, sort_keys=True)
    tmp_path = secrets_path.with_suffix(".yaml.tmp")
    tmp_path.write_text(plain_yaml, encoding="utf-8")
    try:
        subprocess.run(
            [
                "sops",
                "-e",
                "-i",
                # Force YAML handling: the temp file ends in ".yaml.tmp", so
                # sops infers the ".tmp" extension as *binary* and wraps the
                # whole document under a single `data:` key. That made the
                # round-trip return {"data": "<yaml string>"} instead of the
                # flat {key: value} map, so read_secret()/boot_load() found
                # nothing and every deployment silently fell back to plaintext
                # .env (no encryption-at-rest). Pinning the types fixes it.
                "--input-type",
                "yaml",
                "--output-type",
                "yaml",
                "--age",
                age_recipient,
                str(tmp_path),
            ],
            env=_sops_env(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        tmp_path.replace(secrets_path)
    except subprocess.CalledProcessError as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise VaultError(
            f"sops encrypt fail: {(exc.stderr or '')[:200]}", transient=False
        ) from exc
    except subprocess.TimeoutExpired as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise VaultError("sops encrypt timeout", transient=True) from exc


def write_secret(key: str, value: str) -> None:
    """Tek bir secret'i upsert (decrypt → update → encrypt)."""
    data = decrypt_all()
    data[key] = value
    encrypt_all(data)


def read_secret(key: str) -> Optional[str]:
    """Read a single secret. After boot, prefer cache.py."""
    return decrypt_all().get(key)


def delete_secret(key: str) -> bool:
    data = decrypt_all()
    if key not in data:
        return False
    del data[key]
    encrypt_all(data)
    return True
