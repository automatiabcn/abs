# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Encrypted secrets vault paketi (sops + age)."""

from .runner import (
    VaultError,
    decrypt_all,
    delete_secret,
    encrypt_all,
    master_key_exists,
    read_secret,
    sops_available,
    write_secret,
)

__all__ = [
    "VaultError",
    "sops_available",
    "master_key_exists",
    "decrypt_all",
    "encrypt_all",
    "read_secret",
    "write_secret",
    "delete_secret",
]
