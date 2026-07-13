from __future__ import annotations

import json

import pytest

from app.marketplace.manifest_schema import (
    PluginManifest,
    PluginPermissions,
    PluginType,
)
from app.marketplace.registry import (
    PluginRef,
    PluginRegistry,
    PluginSourceKind,
    RegistryError,
    VersionConstraintError,
    _matches_constraint,
    _semver_tuple,
)


def _build_manifest_bytes(version: str = "1.0.0") -> bytes:
    manifest = PluginManifest(
        id="test-plugin",
        name="Test Plugin",
        version=version,
        type=PluginType.LLM_PROVIDER,
        entry_point="ghcr.io/x/y:1",
        description="d",
        author="ABS",
        permissions=PluginPermissions(),
    )
    return json.dumps(manifest.model_dump(mode="json")).encode()


class FakeSource:
    def __init__(
        self,
        kind: PluginSourceKind,
        versions: list[str],
        manifests: dict[str, bytes],
        with_signature: bool = True,
    ) -> None:
        self.kind = kind
        self._versions = versions
        self._manifests = manifests
        self._with_signature = with_signature

    async def list_versions(self, plugin_id: str) -> list[str]:
        return list(self._versions)

    async def fetch_manifest(self, plugin_id: str, version: str) -> bytes:
        return self._manifests[version]

    def to_ref(self, plugin_id: str, version: str) -> PluginRef:
        sig_url = (
            f"https://example/{plugin_id}/{version}.sig"
            if self._with_signature
            else None
        )
        return PluginRef(
            id=plugin_id,
            version=version,
            source=self.kind,
            download_url=f"https://example/{plugin_id}/{version}",
            signature_url=sig_url,
        )


class BadSource:
    def __init__(self, kind: PluginSourceKind) -> None:
        self.kind = kind

    async def list_versions(self, plugin_id: str) -> list[str]:
        raise RuntimeError("source failure")

    async def fetch_manifest(self, plugin_id: str, version: str) -> bytes:
        raise RuntimeError("unreachable")

    def to_ref(self, plugin_id: str, version: str) -> PluginRef:
        raise RuntimeError("unreachable")


def test_semver_tuple_release_higher_than_prerelease():
    assert _semver_tuple("1.2.3") > _semver_tuple("1.2.3-rc.1")


def test_semver_tuple_invalid_raises():
    with pytest.raises(ValueError):
        _semver_tuple("not-a-version")


def test_semver_tuple_basic():
    assert _semver_tuple("2.5.7") == (2, 5, 7, 0, "")


@pytest.mark.parametrize("version", ["1.2.3", "0.0.1"])
def test_matches_constraint_star(version):
    assert _matches_constraint(version, "*") is True


@pytest.mark.parametrize(
    "version,expected",
    [("1.2.3", True), ("1.2.4", False)],
)
def test_matches_constraint_exact_match(version, expected):
    assert _matches_constraint(version, "1.2.3") is expected


@pytest.mark.parametrize("version", ["1.2.3", "1.5.0", "1.99.99"])
def test_matches_constraint_caret_in_range(version):
    assert _matches_constraint(version, "^1.2.3")


@pytest.mark.parametrize("version", ["2.0.0", "1.2.2"])
def test_matches_constraint_caret_out_of_range(version):
    assert not _matches_constraint(version, "^1.2.3")


def test_matches_constraint_caret_zero_minor():
    assert _matches_constraint("0.2.5", "^0.2.3")
    assert not _matches_constraint("0.3.0", "^0.2.3")


@pytest.mark.parametrize("version", ["1.2.3", "1.2.99"])
def test_matches_constraint_tilde_in_range(version):
    assert _matches_constraint(version, "~1.2.3")


def test_matches_constraint_tilde_out_of_range():
    assert not _matches_constraint("1.3.0", "~1.2.3")


def test_matches_constraint_invalid_constraint():
    assert _matches_constraint("1.2.3", "@1") is False


async def test_discover_aggregates_and_dedupes_by_source_version():
    manifests = {"1.0.0": _build_manifest_bytes()}
    src1 = FakeSource(PluginSourceKind.GITHUB_RELEASES, ["1.0.0"], manifests)
    src2 = FakeSource(PluginSourceKind.VERDACCIO, ["1.0.0"], manifests)
    refs = await PluginRegistry([src1, src2]).discover("test-plugin")
    assert len(refs) == 2
    assert {r.source for r in refs} == {
        PluginSourceKind.GITHUB_RELEASES,
        PluginSourceKind.VERDACCIO,
    }


async def test_discover_sorts_descending():
    versions = ["1.0.0", "1.2.3", "0.9.0"]
    manifests = {v: _build_manifest_bytes(v) for v in versions}
    src = FakeSource(PluginSourceKind.GITHUB_RELEASES, versions, manifests)
    refs = await PluginRegistry([src]).discover("test-plugin")
    assert [r.version for r in refs] == ["1.2.3", "1.0.0", "0.9.0"]


async def test_discover_source_failure_swallowed():
    good = FakeSource(
        PluginSourceKind.VERDACCIO, ["1.0.0"], {"1.0.0": _build_manifest_bytes()}
    )
    bad = BadSource(PluginSourceKind.GITHUB_RELEASES)
    refs = await PluginRegistry([bad, good]).discover("test-plugin")
    assert len(refs) == 1
    assert refs[0].source == PluginSourceKind.VERDACCIO


async def test_resolve_star_picks_highest():
    versions = ["1.0.0", "1.2.3", "0.9.0"]
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        versions,
        {v: _build_manifest_bytes(v) for v in versions},
    )
    ref = await PluginRegistry([src]).resolve("test-plugin", constraint="*")
    assert ref.version == "1.2.3"


async def test_resolve_exact():
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        ["1.0.0", "2.0.0"],
        {
            "1.0.0": _build_manifest_bytes("1.0.0"),
            "2.0.0": _build_manifest_bytes("2.0.0"),
        },
    )
    ref = await PluginRegistry([src]).resolve("test-plugin", constraint="1.0.0")
    assert ref.version == "1.0.0"


async def test_resolve_caret_picks_highest_in_range():
    versions = ["1.0.0", "1.2.3", "2.0.0"]
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        versions,
        {v: _build_manifest_bytes(v) for v in versions},
    )
    ref = await PluginRegistry([src]).resolve("test-plugin", constraint="^1.0.0")
    assert ref.version == "1.2.3"


async def test_resolve_no_match_raises():
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        ["1.0.0"],
        {"1.0.0": _build_manifest_bytes()},
    )
    with pytest.raises(VersionConstraintError):
        await PluginRegistry([src]).resolve("test-plugin", constraint="^2.0.0")


async def test_resolve_prefer_source():
    manifests = {"1.0.0": _build_manifest_bytes()}
    gh = FakeSource(PluginSourceKind.GITHUB_RELEASES, ["1.0.0"], manifests)
    vd = FakeSource(PluginSourceKind.VERDACCIO, ["1.0.0"], manifests)
    ref = await PluginRegistry([gh, vd]).resolve(
        "test-plugin", constraint="1.0.0", prefer_source=PluginSourceKind.VERDACCIO
    )
    assert ref.source == PluginSourceKind.VERDACCIO


async def test_fetch_manifest_signed_ref_ok():
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        ["1.0.0"],
        {"1.0.0": _build_manifest_bytes()},
        with_signature=True,
    )
    registry = PluginRegistry([src])
    ref = src.to_ref("test-plugin", "1.0.0")
    manifest = await registry.fetch_manifest(ref)
    assert isinstance(manifest, PluginManifest)
    assert manifest.version == "1.0.0"


async def test_fetch_manifest_unsigned_raises():
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        ["1.0.0"],
        {"1.0.0": _build_manifest_bytes()},
        with_signature=False,
    )
    registry = PluginRegistry([src], allow_unsigned=False)
    ref = src.to_ref("test-plugin", "1.0.0")
    with pytest.raises(RegistryError, match="unsigned manifest"):
        await registry.fetch_manifest(ref)


async def test_fetch_manifest_allow_unsigned_passes():
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        ["1.0.0"],
        {"1.0.0": _build_manifest_bytes()},
        with_signature=False,
    )
    registry = PluginRegistry([src], allow_unsigned=True)
    ref = src.to_ref("test-plugin", "1.0.0")
    assert isinstance(await registry.fetch_manifest(ref), PluginManifest)


async def test_fetch_manifest_unknown_source_kind():
    ref = PluginRef(
        id="test-plugin",
        version="1.0.0",
        source=PluginSourceKind.LOCAL,
        download_url="file:///tmp/plugin.zip",
        signature_url=None,
    )
    with pytest.raises(RegistryError, match="no source registered"):
        await PluginRegistry([], allow_unsigned=True).fetch_manifest(ref)


async def test_check_for_updates_returns_diff():
    versions = ["1.0.0", "1.2.3"]
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        versions,
        {v: _build_manifest_bytes(v) for v in versions},
    )
    updates = await PluginRegistry([src]).check_for_updates({"test-plugin": "1.0.0"})
    assert updates == [("test-plugin", "1.0.0", "1.2.3")]


async def test_check_for_updates_no_updates_returns_empty():
    versions = ["1.0.0", "1.2.3"]
    src = FakeSource(
        PluginSourceKind.GITHUB_RELEASES,
        versions,
        {v: _build_manifest_bytes(v) for v in versions},
    )
    updates = await PluginRegistry([src]).check_for_updates({"test-plugin": "1.2.3"})
    assert updates == []
