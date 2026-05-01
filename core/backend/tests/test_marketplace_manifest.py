from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

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


def _valid_manifest_kwargs() -> dict:
    return {
        "id": "my-plugin",
        "name": "My Plugin",
        "version": "1.0.0",
        "type": PluginType.LLM_PROVIDER,
        "entry_point": "ghcr.io/foo/bar:1.0.0",
        "description": "A test plugin",
        "author": "ABS",
        "homepage": None,
        "license": "Apache-2.0",
        "dependencies": [],
        "permissions": PluginPermissions(),
        "config_schema": {},
        "signature": None,
    }


def _sig_for(payload: bytes, cert: str = "dummy_cert", bundle: str = "dummy_bundle") -> PluginSignature:
    return PluginSignature(
        cosign_bundle=bundle,
        certificate_chain=cert,
        signed_payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_valid_manifest_happy_path():
    manifest = PluginManifest(**_valid_manifest_kwargs())
    assert manifest.id == "my-plugin"
    assert manifest.type == PluginType.LLM_PROVIDER
    assert manifest.version == "1.0.0"
    assert manifest.license == "Apache-2.0"


@pytest.mark.parametrize(
    "bad_id",
    ["MyPlugin", "ab", "1plugin", "my plugin", "my!plugin", "a" * 65],
)
def test_invalid_id_formats(bad_id):
    kwargs = _valid_manifest_kwargs()
    kwargs["id"] = bad_id
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


@pytest.mark.parametrize(
    "bad_version",
    ["1.2", "v1.2.3", "1.2.3.4", "1.2.3-beta!", "1.2.3+build!"],
)
def test_invalid_semver_formats(bad_version):
    kwargs = _valid_manifest_kwargs()
    kwargs["version"] = bad_version
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


def test_valid_semver_with_prerelease():
    kwargs = _valid_manifest_kwargs()
    kwargs["version"] = "1.2.3-rc.1+build.42"
    manifest = PluginManifest(**kwargs)
    assert manifest.version == "1.2.3-rc.1+build.42"


@pytest.mark.parametrize(
    "bad_dep",
    ["BadDep@1", "pypi_pkg@", "@^1.0", "pkg@1.0.0beta"],
)
def test_invalid_dependency_format(bad_dep):
    kwargs = _valid_manifest_kwargs()
    kwargs["dependencies"] = [bad_dep]
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


def test_valid_dependency_caret():
    kwargs = _valid_manifest_kwargs()
    kwargs["dependencies"] = ["pydantic@^2.8", "httpx@^0.27"]
    manifest = PluginManifest(**kwargs)
    assert manifest.dependencies == ["pydantic@^2.8", "httpx@^0.27"]


def test_permissions_defaults():
    perms = PluginPermissions()
    assert perms.filesystem_read == ["/app/config"]
    assert perms.filesystem_write == ["/tmp"]
    assert perms.tenant_scoped is True
    assert perms.cpu_quota == 1.0
    assert perms.memory_mb == 512


@pytest.mark.parametrize("cpu", [0.05, 5.0])
def test_permissions_cpu_out_of_range(cpu):
    with pytest.raises(ValidationError):
        PluginPermissions(cpu_quota=cpu)


@pytest.mark.parametrize("mem", [32, 8192])
def test_permissions_memory_out_of_range(mem):
    with pytest.raises(ValidationError):
        PluginPermissions(memory_mb=mem)


def test_permissions_empty_string_in_egress_list():
    with pytest.raises(ValidationError):
        PluginPermissions(network_egress=[""])


@pytest.mark.parametrize("hex_str", ["abc", "0" * 32, "g" * 64])
def test_signature_hex_64_required(hex_str):
    with pytest.raises(ValidationError):
        PluginSignature(
            cosign_bundle="bundle",
            certificate_chain="cert",
            signed_payload_sha256=hex_str,
        )


def test_signature_empty_bundle_rejected():
    with pytest.raises(ValidationError):
        PluginSignature(
            cosign_bundle="",
            certificate_chain="cert",
            signed_payload_sha256="0" * 64,
        )


def test_lifecycle_valid_transitions():
    for src_state, targets in ALLOWED_TRANSITIONS.items():
        for tgt_state in targets:
            validate_lifecycle_transition(src_state, tgt_state)


def test_lifecycle_invalid_transition_registered_to_enabled():
    with pytest.raises(LifecycleTransitionError):
        validate_lifecycle_transition(LifecycleState.REGISTERED, LifecycleState.ENABLED)


def test_lifecycle_terminal_state_uninstalled():
    for tgt_state in LifecycleState:
        if tgt_state is LifecycleState.UNINSTALLED:
            continue
        with pytest.raises(LifecycleTransitionError):
            validate_lifecycle_transition(LifecycleState.UNINSTALLED, tgt_state)


def test_verify_signature_hash_mismatch():
    payload = b"hello world"
    wrong_sig = PluginSignature(
        cosign_bundle="bundle",
        certificate_chain="cert",
        signed_payload_sha256=hashlib.sha256(b"goodbye").hexdigest(),
    )
    assert verify_signature(payload, wrong_sig, public_key_pem=b"dummy") is False


def test_verify_signature_no_public_key():
    payload = b"test"
    sig = _sig_for(payload)
    assert verify_signature(payload, sig, public_key_pem=None) is False


def test_verify_signature_no_cosign_module():
    payload = b"test"
    sig = _sig_for(payload)
    pem = b"-----BEGIN PUBLIC KEY-----\nFAKE\n-----END PUBLIC KEY-----"
    assert verify_signature(payload, sig, public_key_pem=pem) is False


def test_check_permissions_scope_within_allowlist():
    perms = PluginPermissions(network_egress=["example.com"], cpu_quota=1.0, memory_mb=512)
    allowlist = PluginPermissions(
        network_egress=["example.com", "other.example.com"],
        cpu_quota=2.0,
        memory_mb=1024,
        tenant_scoped=True,
    )
    assert check_permissions_scope(perms, allowlist) == []


def test_check_permissions_scope_extra_egress():
    perms = PluginPermissions(network_egress=["evil.example.com"])
    allowlist = PluginPermissions(
        network_egress=["good.example.com"],
        cpu_quota=2.0,
        memory_mb=1024,
    )
    exceeded = check_permissions_scope(perms, allowlist)
    assert exceeded == ["network_egress"]


def test_check_permissions_scope_cpu_excess():
    perms = PluginPermissions(cpu_quota=2.0)
    allowlist = PluginPermissions(cpu_quota=1.0, memory_mb=1024)
    assert check_permissions_scope(perms, allowlist) == ["cpu_quota"]


def test_check_permissions_scope_memory_excess():
    perms = PluginPermissions(memory_mb=2048)
    allowlist = PluginPermissions(cpu_quota=2.0, memory_mb=1024)
    assert check_permissions_scope(perms, allowlist) == ["memory_mb"]


def test_check_permissions_scope_tenant_boundary():
    perms = PluginPermissions(tenant_scoped=True)
    allowlist = PluginPermissions(tenant_scoped=False, cpu_quota=2.0, memory_mb=1024)
    assert "tenant_scoped" in check_permissions_scope(perms, allowlist)
