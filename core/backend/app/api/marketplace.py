# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Plugin marketplace HTTP surface.

Sandbox launch, cosign verification and the Cerbos pre-filter live in the module
layer; this router is the customer-facing surface, and it is four endpoints:

  GET  /v1/marketplace/plugins          -> the reference catalogue
  GET  /v1/marketplace/plugins/{id}     -> one plugin (404 when unknown)
  POST /v1/marketplace/install          -> tenant-scoped install (admin auth)
  GET  /v1/marketplace/installed        -> plugins installed for this organisation

The catalogue is static; install records live in /app/data/marketplace_installs.json.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.config import settings
from app.observability.audit import emit_event
from app.db.session import get_engine
from app.db.models import TenantInstalledPlugin, User
from sqlmodel import Session, select

router = APIRouter(prefix="/v1/marketplace", tags=["marketplace"])
logger = logging.getLogger(__name__)


# ---------- catalog --------------------------------------------------------

PLUGIN_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "slack-receiver",
        "name": "Slack Receiver",
        "version": "1.0.0",
        "summary": "Brings your Slack messages into ABS.",
        "publisher": "automatiabcn",
        "cosign_signature": "MEUCIQDqv4Slack1.0.0demosigSHA256-aa11bb22cc33dd44",
        "sandbox": {
            "mem_mb": 256,
            "cpu_cores": 0.5,
            "egress_allowlist": ["slack.com"],
        },
        "permissions": ["slack:read", "events:emit"],
        "source": "github:automatiabcn/abs-plugin-slack-receiver",
    },
    {
        "id": "gmail-archiver",
        "name": "Gmail Archiver",
        "version": "1.0.0",
        "summary": "Indexes your Gmail threads so you can ask about them.",
        "publisher": "automatiabcn",
        "cosign_signature": "MEUCIQDgmail1.0.0demosigSHA256-bb22cc33dd44ee55",
        "sandbox": {
            "mem_mb": 384,
            "cpu_cores": 0.5,
            "egress_allowlist": ["googleapis.com"],
        },
        "permissions": ["gmail:read", "rag:index"],
        "source": "github:automatiabcn/abs-plugin-gmail-archiver",
    },
    {
        "id": "linear-bridge",
        "name": "Linear Bridge",
        "version": "1.0.0",
        "summary": "Connects your Linear issues to the work ABS tracks.",
        "publisher": "automatiabcn",
        "cosign_signature": "MEUCIQDlinear1.0.0demosigSHA256-cc33dd44ee55ff66",
        "sandbox": {
            "mem_mb": 256,
            "cpu_cores": 0.25,
            "egress_allowlist": ["api.linear.app"],
        },
        "permissions": ["linear:read", "linear:write"],
        "source": "github:automatiabcn/abs-plugin-linear-bridge",
    },
    {
        "id": "notion-sync",
        "name": "Notion Sync",
        "version": "1.0.0",
        "summary": "Keeps your Notion pages searchable from chat.",
        "publisher": "automatiabcn",
        "cosign_signature": "MEUCIQDnotion1.0.0demosigSHA256-dd44ee55ff6677aa",
        "sandbox": {
            "mem_mb": 384,
            "cpu_cores": 0.5,
            "egress_allowlist": ["api.notion.com"],
        },
        "permissions": ["notion:read", "rag:index"],
        "source": "github:automatiabcn/abs-plugin-notion-sync",
    },
    {
        "id": "postgres-mirror",
        "name": "Postgres Mirror",
        "version": "1.0.0",
        "summary": "Mirrors your Postgres tables, read-only.",
        "publisher": "automatiabcn",
        "cosign_signature": "MEUCIQDpgmirror1.0.0demosigSHA256-ee55ff6677aabb88",
        "sandbox": {
            "mem_mb": 512,
            "cpu_cores": 1.0,
            "egress_allowlist": ["*"],  # tenant-supplied DSN
        },
        "permissions": ["db:read"],
        "source": "github:automatiabcn/abs-plugin-postgres-mirror",
    },
]


def _by_id(plugin_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in PLUGIN_CATALOG if p["id"] == plugin_id), None)


# ---------- install store --------------------------------------------------


def _installs_path() -> Path:
    return Path(settings.data_dir) / "marketplace_installs.json"


def _read_installs() -> Dict[str, List[Dict[str, Any]]]:
    p = _installs_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("marketplace_installs.json unreadable: %s", exc)
    return {}


def _write_installs(state: Dict[str, List[Dict[str, Any]]]) -> None:
    p = _installs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- SQL persistence ------------------------------------------------


def _select_active_install(db: "Session", tenant: str, plugin_id: str):
    return db.exec(
        select(TenantInstalledPlugin).where(
            TenantInstalledPlugin.tenant_id == tenant,
            TenantInstalledPlugin.plugin_id == plugin_id,
            TenantInstalledPlugin.uninstalled_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()


def _persist_install_row(
    *, tenant: str, plugin_id: str, version: str, container_id: Optional[str]
) -> None:
    """Upsert tenant_installed_plugins row for the (tenant, plugin) pair."""
    try:
        with Session(get_engine()) as db:
            existing = _select_active_install(db, tenant, plugin_id)
            if existing is not None:
                return
            row = TenantInstalledPlugin(
                tenant_id=tenant,
                plugin_id=plugin_id,
                version=version,
                sandbox_container_id=container_id,
                installed_at=datetime.now(timezone.utc),
                uninstalled_at=None,
            )
            db.add(row)
            db.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "tenant_installed_plugins persist failed plugin=%s tenant=%s err=%s",
            plugin_id,
            tenant,
            exc,
        )


def _mark_uninstalled_row(*, tenant: str, plugin_id: str) -> None:
    """Mark the active install row as uninstalled (soft-delete)."""
    try:
        with Session(get_engine()) as db:
            row = _select_active_install(db, tenant, plugin_id)
            if row is None:
                return
            row.uninstalled_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "tenant_installed_plugins uninstall mark failed plugin=%s tenant=%s err=%s",
            plugin_id,
            tenant,
            exc,
        )


def _list_installed_rows(tenant: str) -> List[Dict[str, Any]]:
    """SQL view of installed plugins for the tenant; JSON fallback on error."""
    try:
        with Session(get_engine()) as db:
            rows = db.exec(
                select(TenantInstalledPlugin).where(
                    TenantInstalledPlugin.tenant_id == tenant,
                    TenantInstalledPlugin.uninstalled_at.is_(None),  # type: ignore[union-attr]
                )
            ).all()
            out: List[Dict[str, Any]] = []
            for r in rows:
                installed_ts: Optional[float] = None
                if r.installed_at is not None:
                    inst = r.installed_at
                    if inst.tzinfo is None:
                        inst = inst.replace(tzinfo=timezone.utc)
                    installed_ts = inst.timestamp()
                out.append(
                    {
                        "plugin_id": r.plugin_id,
                        "version": r.version,
                        "container_id": r.sandbox_container_id,
                        "installed_at": installed_ts,
                    }
                )
            return out
    except Exception as exc:
        logger.info("tenant_installed_plugins read fell back to JSON: %s", exc)
        return _read_installs().get(tenant, [])


# ---------- request bodies -------------------------------------------------


class InstallBody(BaseModel):
    # Boundary hardening: pre-fix accepted unbounded
    # plugin_id and tenant strings, allowing 1MB+ payloads (DoS) and
    # filesystem traversal (`tenant="../../etc"` → install path
    # escape) since `tenant` lands in a directory path. Pattern caps
    # to a safe charset; max_length caps memory.
    plugin_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    # Optional: when omitted, the tenant is resolved from the admin's identity
    # (same source the installed-list read uses) so a write and its read can't
    # land under different tenants. An explicit value is still honoured for
    # multi-tenant admin tooling and validated against the caller's identity.
    tenant: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )


# ---------- endpoints ------------------------------------------------------


@router.get("/plugins")
async def list_plugins() -> Dict[str, Any]:
    return {"plugins": PLUGIN_CATALOG, "count": len(PLUGIN_CATALOG)}


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str, request: Request) -> Dict[str, Any]:
    plugin = _by_id(plugin_id)
    if not plugin:
        emit_event(
            request,
            action="marketplace.plugin.lookup",
            outcome="denied",
            reason="plugin_not_found",
            plugin_id=plugin_id,
            status_code=404,
        )
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return plugin


def _resolve_admin_tenant(admin: dict) -> str:
    """Resolve tenant for the active admin from
    every available source so bootstrap (setup-wizard) admins are no longer
    forced into the ``"default"`` tenant.

    Resolution order:
      1. JWT ``tenant`` claim — minted by ``auth._create_token`` whenever a
         slug can be inferred at login / magic-link time.
      2. ``users`` table active row — magic-link claim + signup persist this.
      3. ``admin_credentials.json`` cross-check — magic-link claim writes
         ``tenant_slug`` here; setup wizard may also persist it once the
         operator opts in.
      4. Email-domain heuristic — ``admin@demo-acme.com`` → ``demo-acme``
         keeps the bootstrap (file-only) admin scoped without forcing the
         caller to pass an explicit tenant query parameter on every request.
      5. ``"default"`` — last-resort fallback for genuinely tenant-less
         single-host installs (``admin@local``).
    """
    claim = admin.get("tenant")
    if claim:
        return str(claim)
    email = admin.get("sub")
    if not email:
        return "default"

    try:
        with Session(get_engine()) as db:
            stmt = (
                select(User).where(User.email == email).where(User.status == "active")
            )
            user = db.exec(stmt).first()
            if user is not None and user.tenant_slug:
                return str(user.tenant_slug)
    except Exception:  # pragma: no cover — boot before users table
        pass

    try:
        from app.api.auth import _load_admin_credentials_raw

        raw = _load_admin_credentials_raw()
        if raw is not None and raw.get("email") == email:
            slug = raw.get("tenant_slug")
            if slug:
                return str(slug)
    except Exception:  # pragma: no cover — credentials path unavailable
        pass

    # The email-domain heuristic (admin@demo-acme.com → "demo-acme") was removed
    # it diverged from the runtime resolver (`_resolve_tenant` → "default"),
    # silently storing admin-managed entities under a different tenant than the
    # data + queries used. A real tenant comes from the JWT claim, the users
    # table, or admin_credentials.json (steps 1–3); otherwise "default".
    return "default"


def _enforce_tenant_match(
    admin: dict, tenant: str, request: Request | None = None
) -> None:
    """Block cross-tenant queries when admin claim carries a tenant.

    If the admin token has no tenant claim (legacy / single-tenant dev), we
    skip the check so existing flows keep working.

    Strict multi-tenant SaaS (``ABS_MULTI_TENANT_STRICT``) closes that
    fail-open: when the principal carries no explicit ``tenant`` claim we
    resolve its canonical tenant from identity (``_resolve_admin_tenant`` —
    users row / credentials / "default") and compare against THAT, so a
    claim-less admin can no longer install/list under an arbitrary
    client-supplied ``tenant=`` value. Single-tenant deployments leave the
    flag off and keep the legacy skip.
    """
    claim = admin.get("tenant")
    if not claim and settings.multi_tenant_strict:
        claim = _resolve_admin_tenant(admin)
    if claim and claim != tenant:
        if request is not None:
            emit_event(
                request,
                action="marketplace.install.gate",
                outcome="denied",
                reason="cross_tenant_forbidden",
                tenant=tenant,
                claim_tenant=claim,
                status_code=403,
            )
        raise HTTPException(status_code=403, detail="cross_tenant_forbidden")


@router.post("/install", status_code=201)
async def install(
    body: InstallBody,
    request: Request,
    response: Response,
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    # Resolve the tenant from identity unless the caller explicitly overrode it.
    # The installed-list read resolves the same way, so an install and its badge
    # can never land under different tenants.
    tenant = body.tenant or _resolve_admin_tenant(_admin)
    plugin = _by_id(body.plugin_id)
    if not plugin:
        emit_event(
            request,
            action="marketplace.install",
            outcome="denied",
            reason="plugin_not_found",
            plugin_id=body.plugin_id,
            tenant=tenant,
            status_code=404,
        )
        raise HTTPException(status_code=404, detail="plugin_not_found")

    _enforce_tenant_match(_admin, tenant, request)

    # Cosign signature gate (skip-mode by default in dev).
    from app.marketplace.cosign_verify import verify_signature

    # Verify the image we will actually launch. The descriptor's
    # cosign_signature corresponds to its real entry_point image, so when one
    # is published we must gate on that ref — not the local stub. Falls back to
    # the stub ref only when no entry_point is declared (keeps dev/demo working).
    image_ref = plugin.get("entry_point") or f"abs-plugin-stub:{body.plugin_id}"
    if not verify_signature(image_ref, plugin.get("cosign_signature")):
        logger.warning(
            "marketplace_install_signature_invalid plugin=%s tenant=%s",
            body.plugin_id,
            tenant,
        )
        emit_event(
            request,
            action="marketplace.install",
            outcome="denied",
            reason="signature_invalid",
            plugin_id=body.plugin_id,
            tenant=tenant,
            status_code=403,
        )
        raise HTTPException(status_code=403, detail="signature_invalid")

    state = _read_installs()
    bucket = state.setdefault(tenant, [])
    if any(item.get("plugin_id") == body.plugin_id for item in bucket):
        # Idempotent path: 200 OK (no resource created).
        response.status_code = 200
        return {
            "status": "already_installed",
            "plugin_id": body.plugin_id,
            "tenant": tenant,
        }

    install_record: Dict[str, Any] = {
        "plugin_id": body.plugin_id,
        "version": plugin["version"],
        "installed_at": time.time(),
        "installed_by": _admin.get("sub", "admin"),
        "container_id": None,
        "sandbox_status": "installed_no_sandbox",
    }

    # Best-effort sandbox launch. If docker SDK / daemon is
    # unavailable we still persist the install record so the catalog stays
    # consistent (real launch will retry via reconcile loop).
    try:
        from app.marketplace.sandbox import PluginSandbox

        sandbox = PluginSandbox()
        result = sandbox.launch(
            body.plugin_id,
            tenant,
            plugin.get("sandbox", {}),
            image_ref=plugin.get("entry_point"),
        )
        install_record["container_id"] = result.get("container_id")
        install_record["sandbox_status"] = result.get("status", "running")
    except Exception as exc:  # pragma: no cover — graceful in CI / no docker
        # The install record is still written (the catalogue must stay
        # consistent), but it does not get to say the plugin is running.
        #
        # It used to default to `sandbox_status: "running"` on the way out of a
        # *failed* launch — and the launch itself, when the plugin's image could
        # not be pulled, quietly started a busybox stub and called that running
        # too. Two layers, the same lie: a plugin that is not there, reported as
        # up. What is running is now either the plugin's own signed image or
        # nothing, and the record says which.
        logger.warning(
            "marketplace_install_sandbox_failed plugin=%s err=%s",
            body.plugin_id,
            exc,
        )
        # "There is no sandbox on this host" and "the sandbox refused to start
        # this plugin" are different facts, and an operator needs to tell them
        # apart. Neither of them is "running".
        no_docker = isinstance(exc, ImportError) or "docker" in str(exc).lower()
        install_record["sandbox_status"] = (
            "installed_no_sandbox" if no_docker else "not_running"
        )
        install_record["sandbox_error"] = f"{type(exc).__name__}: {exc}"[:300]

    bucket.append(install_record)
    _write_installs(state)
    # Durable SQL persistence so the marketplace UI
    # can reliably distinguish installed plugins after a backend restart.
    _persist_install_row(
        tenant=tenant,
        plugin_id=body.plugin_id,
        version=plugin["version"],
        container_id=install_record.get("container_id"),
    )
    emit_event(
        request,
        action="marketplace.install",
        outcome="success",
        plugin_id=body.plugin_id,
        tenant=tenant,
    )
    logger.info(
        "marketplace_install plugin=%s tenant=%s container=%s",
        body.plugin_id,
        tenant,
        install_record.get("container_id"),
    )
    return {
        "status": "installed",
        "plugin_id": body.plugin_id,
        "tenant": tenant,
        "version": plugin["version"],
        "permissions": plugin["permissions"],
        "container_id": install_record.get("container_id"),
        "sandbox_status": install_record.get("sandbox_status"),
    }


@router.delete("/uninstall/{plugin_id}")
async def uninstall(
    plugin_id: str,
    request: Request,
    tenant: Optional[str] = None,
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    """Tenant-scoped uninstall. Removes the install record and
    best-effort stops the sandbox container."""
    # Resolve from identity unless overridden — matches the install + read paths.
    tenant = tenant or _resolve_admin_tenant(_admin)
    _enforce_tenant_match(_admin, tenant, request)

    state = _read_installs()
    bucket = state.get(tenant, [])
    found = next((i for i in bucket if i.get("plugin_id") == plugin_id), None)
    if not found:
        emit_event(
            request,
            action="marketplace.uninstall",
            outcome="denied",
            reason="not_installed",
            plugin_id=plugin_id,
            tenant=tenant,
            status_code=404,
        )
        raise HTTPException(status_code=404, detail="not_installed")

    state[tenant] = [i for i in bucket if i.get("plugin_id") != plugin_id]
    _write_installs(state)
    # Soft-delete the SQL row so the marketplace UI
    # stops showing the plugin as installed after refresh.
    _mark_uninstalled_row(tenant=tenant, plugin_id=plugin_id)

    sandbox_result: Dict[str, Any] = {"status": "no_sandbox"}
    try:
        from app.marketplace.sandbox import PluginSandbox

        sandbox_result = PluginSandbox().stop(plugin_id, tenant)
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "marketplace_uninstall_sandbox_skipped plugin=%s err=%s",
            plugin_id,
            exc,
        )

    emit_event(
        request,
        action="marketplace.uninstall",
        outcome="success",
        plugin_id=plugin_id,
        tenant=tenant,
    )
    logger.info(
        "marketplace_uninstall plugin=%s tenant=%s sandbox=%s",
        plugin_id,
        tenant,
        sandbox_result.get("status"),
    )
    return {
        "status": "uninstalled",
        "plugin_id": plugin_id,
        "tenant": tenant,
        "sandbox": sandbox_result,
    }


@router.get("/installed")
async def installed(
    tenant: Optional[str] = None,
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    # Resolve from admin's users-row when caller omits the
    # query param so the demo-acme operator does not fall back to the
    # bootstrap "default" tenant and get an empty list.
    resolved = tenant if tenant else _resolve_admin_tenant(_admin)
    _enforce_tenant_match(_admin, resolved)

    # SQL is now authoritative; legacy JSON store is
    # consulted only as a fallback inside `_list_installed_rows` if the
    # tenant_installed_plugins table is unreachable (boot-before-migrate).
    rows = _list_installed_rows(resolved)

    # Best-effort live status enrichment. If docker SDK / daemon
    # is unavailable we just return the persisted records.
    try:
        from app.marketplace.sandbox import PluginSandbox

        sandbox = PluginSandbox()
        enriched = [
            {**row, "live_status": sandbox.status(row["plugin_id"], resolved)}
            for row in rows
        ]
    except Exception:
        enriched = rows

    return {"tenant": resolved, "installed": enriched}
