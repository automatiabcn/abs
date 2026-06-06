# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Multi-tenant Phase 1 — per-owner provider keys + project membership.

Data layer only (additive, opt-in). Existing single-tenant flows are
unchanged: the provider cascade keeps reading global `settings` keys until a
later round wires `resolve_provider_key` into request handling.
"""
