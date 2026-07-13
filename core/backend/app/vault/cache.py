# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""013 — Memory cache; vault'tan boot'ta okunan secrets'larin runtime'da settings'e bind edilmesi."""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


_cache: Dict[str, Any] = {}


# Vault key isimleri → settings attribute eslesmesi
_KEY_MAP = {
    "anthropic_api_key": "anthropic_api_key",
    "groq_api_key": "groq_api_key",
    "cerebras_api_key": "cerebras_api_key",
    "gemini_api_key": "gemini_api_key",
    "cf_account_id": "cf_account_id",
    "cf_api_token": "cf_api_token",
    "cohere_api_key": "cohere_api_key",
    "openrouter_api_key": "openrouter_api_key",
    "stripe_secret_key": "stripe_secret_key",
    "stripe_webhook_secret": "stripe_webhook_secret",
    "license_key": "license_key",
}


def boot_load() -> int:
    """Called at startup: load the secrets out of the vault and into settings."""
    from app.vault.runner import (
        VaultError,
        decrypt_all,
        master_key_exists,
        sops_available,
    )

    if not sops_available() or not master_key_exists():
        logger.info(
            "vault disabled (binary or master key missing) — settings env-from-shell only"
        )
        return 0
    try:
        data = decrypt_all()
    except VaultError as exc:
        logger.warning("vault boot decrypt failed: %s", exc)
        return 0
    loaded = 0
    for vault_key, settings_attr in _KEY_MAP.items():
        if vault_key in data and data[vault_key]:
            setattr(settings, settings_attr, str(data[vault_key]))
            _cache[vault_key] = data[vault_key]
            loaded += 1
    logger.info("vault loaded %d secrets into settings", loaded)
    return loaded


def invalidate() -> None:
    """Rotation sonrasi cache temizle, settings'e yeniden yukle."""
    _cache.clear()
    boot_load()


def known_keys() -> list[str]:
    return list(_KEY_MAP.keys())


def is_loaded(key: str) -> bool:
    return key in _cache


def clear_for_test() -> None:
    """Sadece testlerde kullan — fixture state reset."""
    _cache.clear()
