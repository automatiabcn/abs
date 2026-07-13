# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cerbos PDP client wrapper.

Thin facade over the Cerbos sync HTTP SDK so the rest of the app speaks
in plain dicts. Test code can monkeypatch `_check` to bypass the live
PDP and inject decisions directly.
"""

from __future__ import annotations

import logging
from typing import Any

from cerbos.sdk.client import CerbosClient
from cerbos.sdk.model import Principal, Resource, ResourceAction, ResourceList

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "CerbosUnavailable",
    "build_principal",
    "build_resource",
    "is_allowed",
    "is_allowed_or_raise",
    "check_resources",
]


class CerbosUnavailable(RuntimeError):
    """Raised when the PDP refuses or fails the call (treated as DENY)."""


def _client() -> CerbosClient:
    host = getattr(settings, "cerbos_host", "http://cerbos:3592")
    return CerbosClient(host, timeout_secs=2.0)


def build_principal(
    user_id: str,
    *,
    roles: list[str] | None = None,
    tenant_id: str | None = None,
    extra_attrs: dict[str, Any] | None = None,
) -> Principal:
    attrs: dict[str, Any] = dict(extra_attrs or {})
    if tenant_id is not None:
        attrs.setdefault("tenant_id", tenant_id)
    return Principal(
        id=user_id,
        roles=set(roles or ["member"]),
        attr=attrs,
    )


def build_resource(
    resource_id: str,
    kind: str,
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
    extra_attrs: dict[str, Any] | None = None,
) -> Resource:
    attrs: dict[str, Any] = dict(extra_attrs or {})
    if tenant_id is not None:
        attrs.setdefault("tenant_id", tenant_id)
    if owner_id is not None:
        attrs.setdefault("owner_id", owner_id)
    return Resource(id=resource_id, kind=kind, attr=attrs)


def is_allowed(
    principal: Principal,
    resource: Resource,
    action: str,
    *,
    client: CerbosClient | None = None,
) -> bool:
    """Single-action permission check. Failure of the PDP is treated as DENY."""
    return _check_actions(principal, resource, [action], client=client).get(
        action, False
    )


def is_allowed_or_raise(
    principal: Principal,
    resource: Resource,
    action: str,
    *,
    client: CerbosClient | None = None,
) -> bool:
    """Same as ``is_allowed`` but a transport failure raises
    ``CerbosUnavailable`` instead of returning False, so the
    caller can map it to 503 (vs. 403 for a real policy denial)."""
    own = client is None
    pdp = client or _client()
    try:
        result = pdp.check_resources(
            principal=principal,
            resources=ResourceList(
                resources=[ResourceAction(resource, actions={action})]
            ),
        )
    except Exception as exc:
        if own:
            try:
                pdp.close()
            except Exception:
                pass
        raise CerbosUnavailable(f"cerbos_pdp_unreachable:{type(exc).__name__}") from exc

    if own:
        try:
            pdp.close()
        except Exception:
            pass

    if result.failed():
        raise CerbosUnavailable(f"cerbos_decision_failed:{result.status_code}")
    decision = False
    for entry in result.results:
        decision = entry.is_allowed(action)
    return decision


def check_resources(
    principal: Principal,
    resource: Resource,
    actions: list[str],
    *,
    client: CerbosClient | None = None,
) -> dict[str, bool]:
    """Batch action lookup; returns `{action: allowed_bool}`."""
    return _check_actions(principal, resource, actions, client=client)


def _check_actions(
    principal: Principal,
    resource: Resource,
    actions: list[str],
    *,
    client: CerbosClient | None,
) -> dict[str, bool]:
    own = client is None
    pdp = client or _client()
    try:
        result = pdp.check_resources(
            principal=principal,
            resources=ResourceList(
                resources=[ResourceAction(resource, actions=set(actions))]
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("cerbos_check_failed: %s", exc)
        if own:
            try:
                pdp.close()
            except Exception:
                pass
        return {a: False for a in actions}

    if own:
        try:
            pdp.close()
        except Exception:
            pass

    if result.failed():
        logger.warning("cerbos_decision_failed status=%s", result.status_code)
        return {a: False for a in actions}

    decisions = {a: False for a in actions}
    for entry in result.results:
        for action in actions:
            decisions[action] = entry.is_allowed(action)
    return decisions
