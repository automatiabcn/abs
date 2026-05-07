# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ABS plugin marketplace — manifest, lifecycle, registry, sandbox."""

from app.marketplace.manifest_schema import (
    ALLOWED_TRANSITIONS,
    LifecycleState,
    LifecycleTransitionError,
    PluginManifest,
    PluginPermissions,
    PluginSignature,
    PluginType,
    check_permissions_scope,
    validate_lifecycle_transition,
    verify_signature,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "LifecycleState",
    "LifecycleTransitionError",
    "PluginManifest",
    "PluginPermissions",
    "PluginSignature",
    "PluginType",
    "check_permissions_scope",
    "validate_lifecycle_transition",
    "verify_signature",
]
