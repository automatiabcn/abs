# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Consent Ledger — per-contact channel consent + the outbound gate."""

from app.consent.service import check_channel, get_consent, set_consent

__all__ = ["set_consent", "get_consent", "check_channel"]
