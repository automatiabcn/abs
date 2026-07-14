# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Plaintext .env → encrypted vault migration.

Idempotent: migrates only when a sops master key exists and .env still holds a plaintext key.
The key is removed from .env, written to sops, and the move is recorded in the audit log.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


_PLAIN_ENV_KEYS = (
    "ABS_ANTHROPIC_API_KEY",
    "ABS_GROQ_API_KEY",
    "ABS_CEREBRAS_API_KEY",
    "ABS_GEMINI_API_KEY",
    "ABS_CF_ACCOUNT_ID",
    "ABS_CF_API_TOKEN",
    "ABS_COHERE_API_KEY",
    "ABS_OPENROUTER_API_KEY",
    "ABS_STRIPE_SECRET_KEY",
    "ABS_STRIPE_WEBHOOK_SECRET",
    "ABS_LICENSE_KEY",
)


def _resolve_env_path(env_path: Optional[str] = None) -> Path:
    if env_path:
        return Path(env_path)
    raw = settings.model_config.get("env_file")
    if raw:
        return Path(str(raw))
    return Path(".env")


def migrate_plaintext_env_to_vault(env_path: Optional[str] = None) -> int:
    """Idempotent. Returns how many records were migrated."""
    from app.vault.audit import log_event
    from app.vault.runner import (
        decrypt_all,
        master_key_exists,
        sops_available,
        write_secret,
    )

    if not sops_available() or not master_key_exists():
        return 0

    env_file = _resolve_env_path(env_path)
    if not env_file.is_file():
        return 0

    try:
        existing_vault = decrypt_all()
    except Exception as exc:
        logger.warning("vault migration: decrypt fail: %s", exc)
        return 0

    lines = env_file.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    migrated_count = 0

    for line in lines:
        m = re.match(r"^(ABS_[A-Z0-9_]+)=(.*)$", line)
        if not m:
            new_lines.append(line)
            continue
        env_key, env_val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if env_key not in _PLAIN_ENV_KEYS or not env_val:
            new_lines.append(line)
            continue
        vault_key = env_key[4:].lower()  # ABS_GROQ_API_KEY → groq_api_key
        if vault_key in existing_vault:
            log_event("migration_skip_already_in_vault", vault_key)
            migrated_count += 1
            # Bu satiri atla — .env'den de cikar (vault tek kaynak)
            continue
        try:
            write_secret(vault_key, env_val)
            log_event("migration", vault_key, source="env_plaintext")
            migrated_count += 1
            # Satir new_lines'a eklenmedi — .env'den silindi
        except Exception as exc:
            logger.warning("migration fail %s: %s", env_key, exc)
            new_lines.append(line)

    if migrated_count > 0:
        env_file.write_text(
            "\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8"
        )
        log_event(
            "migration_complete",
            "_aggregate",
            source="env_plaintext",
            count=migrated_count,
        )
    return migrated_count
