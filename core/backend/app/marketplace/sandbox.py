"""Plugin sandbox runtime: spec builder, egress allowlist, Cerbos pre-filter.

Hardened during the G1 sandbox security audit (2026-04-29). Critical
mitigations:
  - Host-path allowlist for read-only and tmpfs mounts (rejects /etc,
    /var/run/docker.sock, etc.)
  - Containers run as a fixed non-root UID with --cap-drop=ALL,
    --security-opt=no-new-privileges, and the default Docker seccomp profile
  - Resource limits validated against permissive bounds before docker run
  - Egress allowlist + host comparisons are case-insensitive and reject
    malformed patterns
  - subprocess.OSError surfaces as SandboxError instead of crashing the worker
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Tuple

from app.marketplace.manifest_schema import PluginManifest

try:  # pragma: no cover — observability is optional in tests
    from app.observability.langfuse_client import langfuse_client  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    langfuse_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

GLOBAL_TENANT = "global"
PLUGIN_BRIDGE_NETWORK = "abs-plugin-net"

# Hardening defaults applied to every plugin container.
SANDBOX_USER = "65534:65534"  # nobody:nogroup
SANDBOX_PIDS_LIMIT = "256"
DEFAULT_CAP_DROP = "ALL"
DEFAULT_SECURITY_OPTS: tuple[str, ...] = (
    "no-new-privileges",
    "seccomp=default",
)

# Mount-path policy. Plugins may only read from /app/config and only write to
# tmpfs at /tmp. Any other host path is rejected.
ALLOWED_RO_MOUNT_PREFIXES: tuple[str, ...] = ("/app/config",)
ALLOWED_TMPFS_PATHS: tuple[str, ...] = ("/tmp",)
DENIED_MOUNT_TOKENS: tuple[str, ...] = (
    "/var/run/docker.sock",
    "/proc",
    "/sys",
    "/etc",
    "/root",
    "/.ssh",
    "..",
)

# Resource bounds that mirror PluginPermissions but are re-checked here so a
# manifest cannot bypass us by skipping Pydantic validation.
MIN_CPU_QUOTA = 0.1
MAX_CPU_QUOTA = 4.0
MIN_MEMORY_MB = 64
MAX_MEMORY_MB = 4096

_HOST_RE = re.compile(r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class SandboxError(RuntimeError):
    """Generic sandbox failure."""


class TenantBoundaryViolation(SandboxError):
    """Plugin invoked outside its tenant scope."""


class EgressDeniedError(SandboxError):
    """Egress destination not on the allowlist."""


class MountPolicyViolation(SandboxError):
    """Manifest requested a mount path outside the sandbox allowlist."""


class ResourceLimitViolation(SandboxError):
    """Manifest requested a CPU/memory quota outside the allowed bounds."""


@dataclass(frozen=True)
class SandboxSpec:
    plugin_id: str
    image: str
    cpu_quota: float
    memory_mb: int
    network_allowlist: Tuple[str, ...]
    read_only_mounts: Tuple[str, ...]
    tmpfs_mounts: Tuple[str, ...]
    env: dict[str, str]
    tenant_id: str
    cerbos_resource_kind: str = "marketplace.plugin"


def _validate_mount(path: str, *, allowed_prefixes: tuple[str, ...], kind: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise MountPolicyViolation(f"{kind} mount must be a non-empty string")
    normalised = path.strip()
    for token in DENIED_MOUNT_TOKENS:
        if token in normalised:
            raise MountPolicyViolation(
                f"{kind} mount {path!r} contains forbidden token {token!r}"
            )
    if not any(
        normalised == prefix or normalised.startswith(prefix + "/")
        for prefix in allowed_prefixes
    ):
        raise MountPolicyViolation(
            f"{kind} mount {path!r} is outside the allowed prefixes {allowed_prefixes}"
        )
    return normalised


def _validate_egress_pattern(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise EgressDeniedError(f"egress pattern must be a non-empty string: {pattern!r}")
    norm = pattern.strip().lower()
    if not _HOST_RE.fullmatch(norm):
        raise EgressDeniedError(f"malformed egress pattern: {pattern!r}")
    return norm


def _validate_env(env: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (env or {}).items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise SandboxError("env keys and values must both be strings")
        if "\n" in k or "\n" in v:
            raise SandboxError("env values must not contain newlines")
        out[k] = v
    return out


def build_sandbox_spec(
    manifest: PluginManifest,
    *,
    tenant_id: str,
    env: dict[str, str] | None = None,
) -> SandboxSpec:
    """Validate tenant + permissions + mounts + resources, return SandboxSpec."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise TenantBoundaryViolation("tenant_id must be a non-empty, non-blank string")
    tenant_id = tenant_id.strip()

    if manifest.permissions.tenant_scoped and tenant_id == GLOBAL_TENANT:
        raise TenantBoundaryViolation(
            f"Plugin {manifest.id} is tenant-scoped; global tenant is forbidden"
        )

    cpu = float(manifest.permissions.cpu_quota)
    memory = int(manifest.permissions.memory_mb)
    if not (MIN_CPU_QUOTA <= cpu <= MAX_CPU_QUOTA):
        raise ResourceLimitViolation(
            f"cpu_quota={cpu} outside [{MIN_CPU_QUOTA}, {MAX_CPU_QUOTA}]"
        )
    if not (MIN_MEMORY_MB <= memory <= MAX_MEMORY_MB):
        raise ResourceLimitViolation(
            f"memory_mb={memory} outside [{MIN_MEMORY_MB}, {MAX_MEMORY_MB}]"
        )

    ro_mounts = tuple(
        _validate_mount(p, allowed_prefixes=ALLOWED_RO_MOUNT_PREFIXES, kind="read_only")
        for p in manifest.permissions.filesystem_read
    )
    tmp_mounts = tuple(
        _validate_mount(p, allowed_prefixes=ALLOWED_TMPFS_PATHS, kind="tmpfs")
        for p in manifest.permissions.filesystem_write
    )
    network = tuple(_validate_egress_pattern(p) for p in manifest.permissions.network_egress)

    merged_env = _validate_env(env)
    merged_env["PLUGIN_ID"] = manifest.id
    merged_env["PLUGIN_VERSION"] = manifest.version
    merged_env["TENANT_ID"] = tenant_id

    return SandboxSpec(
        plugin_id=manifest.id,
        image=manifest.entry_point,
        cpu_quota=cpu,
        memory_mb=memory,
        network_allowlist=network,
        read_only_mounts=ro_mounts,
        tmpfs_mounts=tmp_mounts,
        env=merged_env,
        tenant_id=tenant_id,
    )


def enforce_egress(host: str, spec: SandboxSpec) -> None:
    """Raise EgressDeniedError when *host* is not on the spec allowlist.

    Allowlist patterns:
      - Exact FQDN: "api.example.com"
      - Wildcard subdomain: "*.example.com" (matches a.example.com, but NOT example.com)

    Hostnames are matched case-insensitively.
    """
    if not isinstance(host, str) or not host.strip():
        raise EgressDeniedError("egress host must be a non-empty string")
    host_norm = host.strip().lower()

    if not spec.network_allowlist:
        raise EgressDeniedError(f"Egress to {host!r} denied: empty allowlist")

    for pattern in spec.network_allowlist:
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            apex = suffix.lstrip(".")
            if host_norm.endswith(suffix) and host_norm != apex:
                return
            continue
        if pattern == host_norm:
            return

    raise EgressDeniedError(f"Egress to {host!r} denied: not in allowlist")


def cerbos_check(
    *,
    principal_tenant: str | None,
    plugin_tenant: str | None,
    action: str = "execute",
) -> bool:
    """Tenant-boundary pre-filter. True only when both tenants match (T-005/T-012)."""
    if (
        isinstance(principal_tenant, str)
        and principal_tenant
        and principal_tenant == plugin_tenant
    ):
        return True
    logger.warning(
        "cerbos_pre_filter_deny principal=%s plugin=%s action=%s",
        principal_tenant,
        plugin_tenant,
        action,
    )
    return False


class DockerSandboxLauncher:
    """Adapter that renders a hardened `docker run` argv and delegates exec."""

    def __init__(
        self,
        runner: Callable[[list[str], dict[str, str]], int] | None = None,
        *,
        image_pull_check: Callable[[str], bool] | None = None,
    ) -> None:
        self._runner = runner
        self._image_pull_check = image_pull_check

    def render_argv(self, spec: SandboxSpec) -> list[str]:
        argv: list[str] = [
            "docker",
            "run",
            "--rm",
            "--user",
            SANDBOX_USER,
            "--cap-drop",
            DEFAULT_CAP_DROP,
            "--pids-limit",
            SANDBOX_PIDS_LIMIT,
            "--cpus",
            f"{spec.cpu_quota}",
            "--memory",
            f"{spec.memory_mb}m",
            "--read-only",
            "--tmpfs",
            "/tmp",
        ]
        for opt in DEFAULT_SECURITY_OPTS:
            argv.extend(["--security-opt", opt])

        for mount in dict.fromkeys(spec.tmpfs_mounts):  # dedupe, preserve order
            if mount == "/tmp":
                continue
            argv.extend(["--tmpfs", mount])

        for ro_path in dict.fromkeys(spec.read_only_mounts):
            argv.extend(["-v", f"{ro_path}:{ro_path}:ro"])

        argv.extend(["--network", PLUGIN_BRIDGE_NETWORK])

        for key, value in spec.env.items():
            argv.extend(["-e", f"{key}={value}"])

        argv.extend(
            [
                "--label",
                f"abs.plugin.id={spec.plugin_id}",
                "--label",
                f"abs.tenant.id={spec.tenant_id}",
                "--label",
                f"abs.egress.allowlist={','.join(spec.network_allowlist)}",
            ]
        )
        argv.append(spec.image)
        return argv

    def launch(self, spec: SandboxSpec) -> int:
        if self._image_pull_check is not None and not self._image_pull_check(spec.image):
            raise SandboxError(f"image not available: {spec.image}")

        if self._runner is None:
            raise SandboxError("no runner configured (dry-run mode)")

        argv = self.render_argv(spec)

        trace = None
        if langfuse_client is not None:
            try:
                trace = langfuse_client.start_trace(  # type: ignore[union-attr]
                    name="plugin_execution",
                    metadata={
                        "plugin_id": spec.plugin_id,
                        "tenant_id": spec.tenant_id,
                        "image": spec.image,
                    },
                )
            except Exception:  # pragma: no cover
                trace = None

        try:
            return self._runner(argv, dict(spec.env))
        finally:
            if trace is not None:
                try:  # pragma: no cover
                    trace.end()
                except Exception:
                    pass


def _subprocess_runner(argv: list[str], env: dict[str, str]) -> int:
    try:
        completed = subprocess.run(argv, env=env, capture_output=True, text=True)
    except OSError as exc:
        raise SandboxError(f"docker exec failed: {type(exc).__name__}: {exc}") from exc
    return completed.returncode


def create_default_launcher() -> DockerSandboxLauncher:
    """Production launcher wired to subprocess `docker run`."""
    return DockerSandboxLauncher(runner=_subprocess_runner)


__all__ = [
    "ALLOWED_RO_MOUNT_PREFIXES",
    "ALLOWED_TMPFS_PATHS",
    "DENIED_MOUNT_TOKENS",
    "DockerSandboxLauncher",
    "EgressDeniedError",
    "GLOBAL_TENANT",
    "MAX_CPU_QUOTA",
    "MAX_MEMORY_MB",
    "MIN_CPU_QUOTA",
    "MIN_MEMORY_MB",
    "MountPolicyViolation",
    "PLUGIN_BRIDGE_NETWORK",
    "PluginSandbox",
    "ResourceLimitViolation",
    "SANDBOX_USER",
    "SandboxError",
    "SandboxSpec",
    "TenantBoundaryViolation",
    "build_sandbox_spec",
    "cerbos_check",
    "create_default_launcher",
    "enforce_egress",
]


# ==========================================================================
# Q7 Phase B — Real Docker launcher / monitor
# ==========================================================================

import time  # noqa: E402  (kept module-local for the Q7 launcher block)
from typing import Any, Dict, Optional  # noqa: E402

try:  # pragma: no cover — docker SDK is optional in CI / dev
    import docker  # type: ignore
    from docker.errors import APIError, NotFound  # type: ignore
except ImportError:  # pragma: no cover
    docker = None  # type: ignore
    APIError = NotFound = Exception  # type: ignore


class PluginSandbox:
    """Tenant-scoped Docker plugin launcher (Q7 Phase B).

    Wraps ``docker.from_env()`` and labels every container with
    ``abs.plugin=<id>`` + ``abs.tenant=<tid>`` for safe tenant isolation.

    The class only manages *real* container lifecycle — manifest validation,
    egress allowlists and Cerbos pre-filtering remain in
    :func:`build_sandbox_spec` / :class:`DockerSandboxLauncher` upstream.
    Q8 will wire this into the install flow with full image-pull policies and
    cosign verification on the launched image.
    """

    def __init__(self) -> None:
        if docker is None:
            raise RuntimeError("docker SDK not installed")
        self.client = docker.from_env()

    # ---- helpers --------------------------------------------------------
    def _name(self, plugin_id: str, tenant_id: str) -> str:
        return f"abs-plugin-{tenant_id}-{plugin_id}"

    def _image(self, plugin_id: str) -> str:
        # Q7 stub: use busybox stub built locally; real ghcr.io image in Q8.
        return f"abs-plugin-stub:{plugin_id}"

    # ---- lifecycle ------------------------------------------------------
    def launch(
        self,
        plugin_id: str,
        tenant_id: str,
        sandbox_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Start (or re-start) a labelled container for *plugin_id* in *tenant_id*.

        Returns a status dict with at least ``status`` and ``container_id``.
        Idempotent: a running container short-circuits with
        ``status="already_running"``; a stale (non-running) container with the
        same name is force-removed before re-launch.
        """
        name = self._name(plugin_id, tenant_id)
        try:
            existing = self.client.containers.get(name)
            if existing.status == "running":
                return {
                    "status": "already_running",
                    "container_id": existing.id,
                    "name": name,
                }
            existing.remove(force=True)
        except NotFound:
            pass

        mem_mb = int(sandbox_profile.get("mem_mb", 256))
        cpu_cores = float(sandbox_profile.get("cpu_cores", 0.5))
        container = self.client.containers.run(
            image=self._image(plugin_id),
            name=name,
            detach=True,
            mem_limit=f"{mem_mb}m",
            nano_cpus=int(cpu_cores * 1e9),
            network_mode="bridge",
            environment={
                "ABS_TENANT_ID": tenant_id,
                "ABS_PLUGIN_ID": plugin_id,
            },
            labels={
                "abs.plugin": plugin_id,
                "abs.tenant": tenant_id,
                "abs.managed": "q7",
            },
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=False,
            restart_policy={"Name": "unless-stopped"},
        )
        return {
            "status": "running",
            "container_id": container.id,
            "name": name,
            "started_at": time.time(),
        }

    def stop(self, plugin_id: str, tenant_id: str) -> Dict[str, Any]:
        """Stop + remove the container; idempotent (returns ``not_running``)."""
        name = self._name(plugin_id, tenant_id)
        try:
            c = self.client.containers.get(name)
            c.stop(timeout=10)
            c.remove(force=True)
            return {"status": "stopped", "name": name}
        except NotFound:
            return {"status": "not_running", "name": name}

    def status(self, plugin_id: str, tenant_id: str) -> Dict[str, Any]:
        """Return live container status (or ``not_running``)."""
        name = self._name(plugin_id, tenant_id)
        try:
            c = self.client.containers.get(name)
            state = c.attrs.get("State", {}) if hasattr(c, "attrs") else {}
            return {
                "status": c.status,
                "container_id": c.id,
                "started_at": state.get("StartedAt"),
                "health": (state.get("Health") or {}).get("Status"),
            }
        except NotFound:
            return {"status": "not_running"}
