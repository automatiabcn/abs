"""Marketplace — entry_point image ref must not become docker argv injection.

The sandbox renders `docker run ... <image>` with the image as the final
positional arg and no `--` separator. A manifest entry_point of "--privileged"
(or a path / whitespace value) would be parsed by docker as a flag. Two layers
defend this: the manifest validator (reject at load) and render_argv (reject at
the exec boundary even if a SandboxSpec is built directly).
"""

import pytest

import app.marketplace.sandbox as sandbox_mod
from app.marketplace.manifest_schema import _IMAGE_REF_RE


# ---- manifest validator (regex) --------------------------------------------

@pytest.mark.parametrize(
    "ref",
    [
        "ghcr.io/abs-plugins/slack-thread-rag:1.0.0",
        "ghcr.io/abs-plugins/notion-sync:1.0.0",
        "nginx:latest",
        "busybox",
        "registry.example.com:5000/team/app:v2.3.4",
        "repo/app@sha256:" + "a" * 64,
    ],
)
def test_valid_image_refs_accepted(ref):
    assert _IMAGE_REF_RE.fullmatch(ref) is not None


@pytest.mark.parametrize(
    "ref",
    [
        "--privileged",
        "-v/host:/host",
        "--network=host",
        "image with space",
        "UPPER/CASE:tag",          # repo must be lowercase
        "  leading-space:tag",
        "-",
        "",
    ],
)
def test_flag_like_or_dirty_refs_rejected(ref):
    assert _IMAGE_REF_RE.fullmatch(ref) is None


def test_manifest_rejects_flag_entry_point():
    from pydantic import ValidationError

    from app.marketplace.manifest_schema import PluginManifest

    base = {
        "id": "evil-plugin",
        "name": "Evil",
        "version": "1.0.0",
        "type": "rag-source",
        "entry_point": "--privileged",
        "description": "x",
        "author": "a",
        "permissions": {
            "network_egress": [],
            "filesystem_read": [],
            "filesystem_write": [],
            "secrets": [],
            "tenant_scoped": True,
            "cpu_quota": 0.5,
            "memory_mb": 256,
        },
    }
    with pytest.raises(ValidationError):
        PluginManifest(**base)


# ---- render_argv exec-boundary guard ---------------------------------------

def _spec(image):
    return sandbox_mod.SandboxSpec(
        plugin_id="p",
        image=image,
        cpu_quota=0.5,
        memory_mb=256,
        network_allowlist=("api.example.com",),
        read_only_mounts=(),
        tmpfs_mounts=(),
        env={},
        tenant_id="t1",
    )


def test_render_argv_rejects_flag_image():
    launcher = sandbox_mod.DockerSandboxLauncher()
    for bad in ("--privileged", "-v/:/host", "im age"):
        with pytest.raises(sandbox_mod.SandboxError):
            launcher.render_argv(_spec(bad))


def test_render_argv_accepts_clean_image_and_image_is_last():
    launcher = sandbox_mod.DockerSandboxLauncher()
    argv = launcher.render_argv(_spec("ghcr.io/abs-plugins/x:1.0.0"))
    assert argv[-1] == "ghcr.io/abs-plugins/x:1.0.0"
    assert argv[0:2] == ["docker", "run"]
    # hardening flags present
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--read-only" in argv
    assert "--no-new-privileges" in " ".join(argv) or "no-new-privileges" in argv
