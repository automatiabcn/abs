from __future__ import annotations

import dataclasses
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.marketplace.manifest_schema import PluginManifest, PluginPermissions, PluginType
from app.marketplace.sandbox import (
    DockerSandboxLauncher,
    EgressDeniedError,
    GLOBAL_TENANT,
    PLUGIN_BRIDGE_NETWORK,
    SandboxError,
    TenantBoundaryViolation,
    build_sandbox_spec,
    cerbos_check,
    enforce_egress,
)


def _manifest(perms_kw: dict | None = None, **overrides) -> PluginManifest:
    perms = PluginPermissions(**(perms_kw or {}))
    base: dict = dict(
        id="my-plugin",
        name="My Plugin",
        version="1.2.3",
        type=PluginType.LLM_PROVIDER,
        entry_point="ghcr.io/abs/echo:1.0.0",
        description="d",
        author="ABS",
        permissions=perms,
    )
    base.update(overrides)
    return PluginManifest(**base)


def _spec(**overrides) -> SimpleNamespace:
    base: dict = dict(
        plugin_id="my-plugin",
        image="ghcr.io/abs/echo:1.0.0",
        cpu_quota=0.5,
        memory_mb=256,
        tenant_id="acme",
        read_only_mounts=(),
        tmpfs_mounts=(),
        network_allowlist=(),
        env={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_sandbox_spec_basic():
    spec = build_sandbox_spec(_manifest(), tenant_id="acme")
    assert spec.plugin_id == "my-plugin"
    assert spec.image == "ghcr.io/abs/echo:1.0.0"
    assert isinstance(spec.cpu_quota, float)
    assert isinstance(spec.memory_mb, int)
    assert spec.tenant_id == "acme"


def test_build_sandbox_spec_env_merge():
    spec = build_sandbox_spec(
        _manifest(),
        tenant_id="acme",
        env={"FOO": "bar", "PLUGIN_ID": "hijack"},
    )
    assert spec.env["FOO"] == "bar"
    assert spec.env["PLUGIN_ID"] == "my-plugin"
    assert spec.env["TENANT_ID"] == "acme"
    assert spec.env["PLUGIN_VERSION"] == "1.2.3"


def test_build_sandbox_spec_empty_tenant_raises():
    with pytest.raises(TenantBoundaryViolation):
        build_sandbox_spec(_manifest(), tenant_id="")


def test_build_sandbox_spec_global_tenant_blocked_when_scoped():
    with pytest.raises(TenantBoundaryViolation):
        build_sandbox_spec(_manifest(), tenant_id=GLOBAL_TENANT)


def test_build_sandbox_spec_global_tenant_allowed_when_unscoped():
    spec = build_sandbox_spec(
        _manifest(perms_kw={"tenant_scoped": False}),
        tenant_id=GLOBAL_TENANT,
    )
    assert spec.tenant_id == GLOBAL_TENANT


def test_build_sandbox_spec_immutable():
    spec = build_sandbox_spec(_manifest(), tenant_id="acme")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.cpu_quota = 1  # type: ignore[misc]


def test_build_sandbox_spec_lists_become_tuples():
    manifest = _manifest(
        perms_kw={
            "filesystem_read": ["/app/config"],
            "filesystem_write": ["/tmp"],
            "network_egress": ["api.example.com"],
        }
    )
    spec = build_sandbox_spec(manifest, tenant_id="acme")
    assert isinstance(spec.read_only_mounts, tuple)
    assert isinstance(spec.tmpfs_mounts, tuple)
    assert isinstance(spec.network_allowlist, tuple)
    assert spec.network_allowlist == ("api.example.com",)


def test_egress_empty_allowlist_denies_all():
    spec = _spec(network_allowlist=())
    with pytest.raises(EgressDeniedError):
        enforce_egress("api.example.com", spec)


def test_egress_exact_match():
    spec = _spec(network_allowlist=("api.example.com",))
    enforce_egress("api.example.com", spec)


def test_egress_wildcard_subdomain_allows_subdomain():
    spec = _spec(network_allowlist=("*.example.com",))
    enforce_egress("api.example.com", spec)


def test_egress_wildcard_does_not_match_apex():
    spec = _spec(network_allowlist=("*.example.com",))
    with pytest.raises(EgressDeniedError):
        enforce_egress("example.com", spec)


def test_egress_wildcard_unrelated_domain_denied():
    spec = _spec(network_allowlist=("*.example.com",))
    with pytest.raises(EgressDeniedError):
        enforce_egress("evil.com", spec)


def test_egress_unknown_host_raises():
    spec = _spec(network_allowlist=("api.example.com",))
    with pytest.raises(EgressDeniedError):
        enforce_egress("evil.com", spec)


def test_cerbos_check_same_tenant():
    assert cerbos_check(principal_tenant="acme", plugin_tenant="acme") is True


def test_cerbos_check_cross_tenant_denied_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        result = cerbos_check(principal_tenant="acme", plugin_tenant="evil")
    assert result is False
    assert any("cerbos_pre_filter_deny" in rec.getMessage() for rec in caplog.records)


def test_cerbos_check_empty_principal_denied():
    assert cerbos_check(principal_tenant="", plugin_tenant="acme") is False


def test_render_argv_basic_includes_run_rm_cpus_memory():
    spec = _spec(cpu_quota=0.5, memory_mb=256)
    argv = DockerSandboxLauncher().render_argv(spec)
    assert argv[0:3] == ["docker", "run", "--rm"]
    assert "--cpus" in argv
    assert argv[argv.index("--cpus") + 1] == "0.5"
    assert "--memory" in argv
    assert argv[argv.index("--memory") + 1] == "256m"


def test_render_argv_includes_read_only_and_tmpfs():
    spec = _spec(tmpfs_mounts=("/tmp",))
    argv = DockerSandboxLauncher().render_argv(spec)
    assert "--read-only" in argv
    assert "--tmpfs" in argv
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"


def test_render_argv_read_only_mounts_emitted():
    spec = _spec(read_only_mounts=("/data", "/config"))
    argv = DockerSandboxLauncher().render_argv(spec)
    for ro in spec.read_only_mounts:
        assert f"{ro}:{ro}:ro" in argv


def test_render_argv_network_uses_bridge():
    spec = _spec()
    argv = DockerSandboxLauncher().render_argv(spec)
    assert "--network" in argv
    assert argv[argv.index("--network") + 1] == PLUGIN_BRIDGE_NETWORK


def test_render_argv_env_pairs():
    spec = _spec(env={"PLUGIN_ID": "my-plugin", "TENANT_ID": "acme", "CUSTOM": "val"})
    argv = DockerSandboxLauncher().render_argv(spec)
    env_pairs = [argv[i + 1] for i, v in enumerate(argv) if v == "-e"]
    assert "PLUGIN_ID=my-plugin" in env_pairs
    assert "TENANT_ID=acme" in env_pairs
    assert "CUSTOM=val" in env_pairs


def test_render_argv_labels_present():
    spec = _spec(network_allowlist=("api.example.com", "db.example.com"))
    argv = DockerSandboxLauncher().render_argv(spec)
    label_vals = [argv[i + 1] for i, v in enumerate(argv) if v == "--label"]
    assert "abs.plugin.id=my-plugin" in label_vals
    assert "abs.tenant.id=acme" in label_vals
    assert "abs.egress.allowlist=api.example.com,db.example.com" in label_vals


def test_render_argv_image_last():
    spec = _spec()
    argv = DockerSandboxLauncher().render_argv(spec)
    assert argv[-1] == spec.image


def test_launch_no_runner_raises():
    with pytest.raises(SandboxError):
        DockerSandboxLauncher().launch(_spec())


def test_launch_image_pull_check_fails():
    launcher = DockerSandboxLauncher(
        runner=MagicMock(return_value=0),
        image_pull_check=lambda img: False,
    )
    with pytest.raises(SandboxError, match="image not available"):
        launcher.launch(_spec(image="nonexistent:image"))


def test_launch_runner_called_with_argv_and_env():
    runner = MagicMock(return_value=0)
    launcher = DockerSandboxLauncher(runner=runner, image_pull_check=lambda img: True)
    spec = _spec(env={"PLUGIN_ID": "my-plugin", "TENANT_ID": "acme", "CUSTOM": "val"})
    assert launcher.launch(spec) == 0
    runner.assert_called_once()
    argv_arg, env_arg = runner.call_args[0]
    assert argv_arg[0] == "docker"
    assert env_arg["PLUGIN_ID"] == "my-plugin"
    assert env_arg["CUSTOM"] == "val"


def test_launch_runner_returns_exit_code():
    runner = MagicMock(return_value=42)
    launcher = DockerSandboxLauncher(runner=runner, image_pull_check=lambda img: True)
    assert launcher.launch(_spec()) == 42
