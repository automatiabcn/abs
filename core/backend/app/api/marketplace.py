"""CJ-008 / Sprint 19 T-S01 — Plugin marketplace HTTP surface.

Sandbox + cosign verification + Cerbos pre-filter karmasik akislari Sprint 19'da
modul katmaninda yer alir; bu router musteri-temas eden 4 endpoint'i acar:

  GET  /v1/marketplace/plugins          → 5 reference plugin
  GET  /v1/marketplace/plugins/{id}     → tek plugin detayi (404 yoksa)
  POST /v1/marketplace/install          → tenant-scoped install (admin auth)
  GET  /v1/marketplace/installed        → admin tenant icin yuklu plugin'ler

Veri kaynagi static katalog (5 plugin); install kayitlari /app/data/marketplace_installs.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.config import settings

router = APIRouter(prefix="/v1/marketplace", tags=["marketplace"])
logger = logging.getLogger(__name__)


# ---------- catalog --------------------------------------------------------

PLUGIN_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "slack-receiver",
        "name": "Slack Receiver",
        "version": "1.0.0",
        "summary": "Slack mesajlarini ABS event-bus'a aktarir.",
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
        "summary": "Gmail thread'lerini RAG indeksine ve sogan-store'a aktarir.",
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
        "summary": "Linear issue'lari ABS task graph'ina baglar.",
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
        "summary": "Notion sayfalarini RAG indeksine senkronize eder.",
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
        "summary": "Postgres tablolarini ABS read-replica olarak yansitir.",
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


# ---------- request bodies -------------------------------------------------


class InstallBody(BaseModel):
    # Q12-L25-001 — boundary hardening: pre-fix accepted unbounded
    # plugin_id and tenant strings, allowing 1MB+ payloads (DoS) and
    # filesystem traversal (`tenant="../../etc"` → install path
    # escape) since `tenant` lands in a directory path. Pattern caps
    # to a safe charset; max_length caps memory.
    plugin_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    tenant: str = Field(
        default="default",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )


# ---------- endpoints ------------------------------------------------------


@router.get("/plugins")
async def list_plugins() -> Dict[str, Any]:
    return {"plugins": PLUGIN_CATALOG, "count": len(PLUGIN_CATALOG)}


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str) -> Dict[str, Any]:
    plugin = _by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return plugin


def _enforce_tenant_match(admin: dict, tenant: str) -> None:
    """Q7 Phase B — block cross-tenant queries when admin claim carries a tenant.

    If the admin token has no tenant claim (legacy / single-tenant dev), we
    skip the check so existing flows keep working.
    """
    claim = admin.get("tenant")
    if claim and claim != tenant:
        raise HTTPException(status_code=403, detail="cross_tenant_forbidden")


@router.post("/install", status_code=201)
async def install(
    body: InstallBody,
    response: Response,
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    plugin = _by_id(body.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin_not_found")

    _enforce_tenant_match(_admin, body.tenant)

    # Q7 Phase B — cosign signature gate (skip-mode by default in dev).
    from app.marketplace.cosign_verify import verify_signature

    image_ref = f"abs-plugin-stub:{body.plugin_id}"
    if not verify_signature(image_ref, plugin.get("cosign_signature")):
        logger.warning(
            "marketplace_install_signature_invalid plugin=%s tenant=%s",
            body.plugin_id,
            body.tenant,
        )
        raise HTTPException(status_code=403, detail="signature_invalid")

    state = _read_installs()
    bucket = state.setdefault(body.tenant, [])
    if any(item.get("plugin_id") == body.plugin_id for item in bucket):
        # Idempotent path: 200 OK (no resource created).
        response.status_code = 200
        return {
            "status": "already_installed",
            "plugin_id": body.plugin_id,
            "tenant": body.tenant,
        }

    install_record: Dict[str, Any] = {
        "plugin_id": body.plugin_id,
        "version": plugin["version"],
        "installed_at": time.time(),
        "installed_by": _admin.get("sub", "admin"),
        "container_id": None,
        "sandbox_status": "installed_no_sandbox",
    }

    # Q7 Phase B — best-effort sandbox launch. If docker SDK / daemon is
    # unavailable we still persist the install record so the catalog stays
    # consistent (real launch will retry in Q8 via reconcile loop).
    try:
        from app.marketplace.sandbox import PluginSandbox

        sandbox = PluginSandbox()
        result = sandbox.launch(
            body.plugin_id, body.tenant, plugin.get("sandbox", {})
        )
        install_record["container_id"] = result.get("container_id")
        install_record["sandbox_status"] = result.get("status", "running")
    except Exception as exc:  # pragma: no cover — graceful in CI / no docker
        logger.warning(
            "marketplace_install_sandbox_skipped plugin=%s err=%s",
            body.plugin_id,
            exc,
        )

    bucket.append(install_record)
    _write_installs(state)
    logger.info(
        "marketplace_install plugin=%s tenant=%s container=%s",
        body.plugin_id,
        body.tenant,
        install_record.get("container_id"),
    )
    return {
        "status": "installed",
        "plugin_id": body.plugin_id,
        "tenant": body.tenant,
        "version": plugin["version"],
        "permissions": plugin["permissions"],
        "container_id": install_record.get("container_id"),
        "sandbox_status": install_record.get("sandbox_status"),
    }


@router.delete("/uninstall/{plugin_id}")
async def uninstall(
    plugin_id: str,
    tenant: str = "default",
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    """Q7 Phase B — tenant-scoped uninstall. Removes the install record and
    best-effort stops the sandbox container."""
    _enforce_tenant_match(_admin, tenant)

    state = _read_installs()
    bucket = state.get(tenant, [])
    found = next((i for i in bucket if i.get("plugin_id") == plugin_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="not_installed")

    state[tenant] = [i for i in bucket if i.get("plugin_id") != plugin_id]
    _write_installs(state)

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
    tenant: str = "default", _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    _enforce_tenant_match(_admin, tenant)

    state = _read_installs()
    rows = state.get(tenant, [])

    # Q7 Phase B — best-effort live status enrichment. If docker SDK / daemon
    # is unavailable we just return the persisted records.
    try:
        from app.marketplace.sandbox import PluginSandbox

        sandbox = PluginSandbox()
        enriched = [
            {**row, "live_status": sandbox.status(row["plugin_id"], tenant)}
            for row in rows
        ]
    except Exception:
        enriched = rows

    return {"tenant": tenant, "installed": enriched}
