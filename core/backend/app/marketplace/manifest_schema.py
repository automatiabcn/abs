"""Plugin manifest schema, lifecycle states, signature + permission helpers."""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, HttpUrl, field_validator


class PluginType(str, Enum):
    LLM_PROVIDER = "llm-provider"
    RAG_SOURCE = "rag-source"
    MCP_TOOL = "mcp-tool"
    WORKFLOW_TEMPLATE = "workflow-template"


class LifecycleState(str, Enum):
    REGISTERED = "REGISTERED"
    INSTALLED = "INSTALLED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    UNINSTALLED = "UNINSTALLED"


ALLOWED_TRANSITIONS: Dict[LifecycleState, Set[LifecycleState]] = {
    LifecycleState.REGISTERED: {LifecycleState.INSTALLED, LifecycleState.UNINSTALLED},
    LifecycleState.INSTALLED: {LifecycleState.ENABLED, LifecycleState.UNINSTALLED},
    LifecycleState.ENABLED: {LifecycleState.DISABLED, LifecycleState.UNINSTALLED},
    LifecycleState.DISABLED: {LifecycleState.ENABLED, LifecycleState.UNINSTALLED},
    LifecycleState.UNINSTALLED: set(),
}


class LifecycleTransitionError(ValueError):
    """Lifecycle transition is not permitted."""


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[\w.-]+)?(?:\+[\w.-]+)?$"
)
_DEP_RE = re.compile(r"^[a-z][a-z0-9_-]+@\^?[\d.]+$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class PluginPermissions(BaseModel):
    """Resource + capability scope a plugin requests at install time."""

    network_egress: List[str] = Field(default_factory=list)
    filesystem_read: List[str] = Field(default_factory=lambda: ["/app/config"])
    filesystem_write: List[str] = Field(default_factory=lambda: ["/tmp"])
    secrets: List[str] = Field(default_factory=list)
    tenant_scoped: bool = True
    cpu_quota: float = Field(1.0, ge=0.1, le=4.0)
    memory_mb: int = Field(512, ge=64, le=4096)

    @field_validator(
        "network_egress",
        "filesystem_read",
        "filesystem_write",
        "secrets",
        mode="before",
    )
    @classmethod
    def _non_empty_str_list(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("must be a list")
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("list items must be non-empty strings")
        return v


class PluginSignature(BaseModel):
    """Cosign signature bundle for an immutable manifest blob."""

    cosign_bundle: str = Field(..., min_length=1)
    certificate_chain: str = Field(..., min_length=1)
    signed_payload_sha256: str

    @field_validator("signed_payload_sha256")
    @classmethod
    def _hex64(cls, v: str) -> str:
        if not _HEX64_RE.fullmatch(v):
            raise ValueError("must be a 64-char hex string")
        return v


class PluginManifest(BaseModel):
    """Top-level marketplace plugin manifest."""

    id: str
    name: str = Field(..., min_length=1, max_length=120)
    version: str
    type: PluginType
    entry_point: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1, max_length=500)
    author: str = Field(..., max_length=120)
    homepage: Optional[HttpUrl] = None
    license: str = "Apache-2.0"
    dependencies: List[str] = Field(default_factory=list)
    permissions: PluginPermissions
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    signature: Optional[PluginSignature] = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _SLUG_RE.fullmatch(v):
            raise ValueError("id must match slug pattern ^[a-z][a-z0-9_-]{2,63}$")
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not _SEMVER_RE.fullmatch(v):
            raise ValueError("version must be valid semver")
        return v

    @field_validator("dependencies", mode="before")
    @classmethod
    def _validate_dependencies(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("dependencies must be a list")
        for dep in v:
            if not isinstance(dep, str) or not _DEP_RE.fullmatch(dep):
                raise ValueError(f"invalid dependency format: {dep!r}")
        return v


def validate_lifecycle_transition(
    current: LifecycleState,
    target: LifecycleState,
) -> None:
    """Raise LifecycleTransitionError when current→target is not allowed."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise LifecycleTransitionError(
            f"Cannot transition from {current.value} to {target.value}"
        )


def verify_signature(
    manifest_bytes: bytes,
    signature: PluginSignature,
    *,
    public_key_pem: bytes | None = None,
) -> bool:
    """Verify cosign-signed manifest bytes; False on missing tooling/key/mismatch."""
    payload_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if payload_hash.lower() != signature.signed_payload_sha256.lower():
        return False

    if public_key_pem is None:
        return False

    try:
        from cosign import verify_blob  # type: ignore[import-not-found]
    except Exception:
        return False

    try:
        verify_blob(
            blob=manifest_bytes,
            bundle=signature.cosign_bundle,
            certificate=signature.certificate_chain,
            public_key=public_key_pem,
        )
        return True
    except Exception:
        return False


def check_permissions_scope(
    perms: PluginPermissions,
    allowlist: PluginPermissions,
) -> List[str]:
    """Return list of permission fields where perms exceed allowlist."""
    exceeded: List[str] = []

    for field_name in ("network_egress", "filesystem_read", "filesystem_write", "secrets"):
        perm_vals = set(getattr(perms, field_name))
        allow_vals = set(getattr(allowlist, field_name))
        if perm_vals - allow_vals:
            exceeded.append(field_name)

    if perms.cpu_quota > allowlist.cpu_quota:
        exceeded.append("cpu_quota")
    if perms.memory_mb > allowlist.memory_mb:
        exceeded.append("memory_mb")
    if perms.tenant_scoped and not allowlist.tenant_scoped:
        exceeded.append("tenant_scoped")

    return exceeded


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
