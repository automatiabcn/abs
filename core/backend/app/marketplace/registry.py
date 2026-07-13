# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Marketplace plugin registry — discovery + version resolve + signed fetch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Protocol, Tuple

import httpx

from app.marketplace.manifest_schema import PluginManifest


class PluginSourceKind(str, Enum):
    GITHUB_RELEASES = "github_releases"
    VERDACCIO = "verdaccio"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class PluginRef:
    id: str
    version: str
    source: PluginSourceKind
    download_url: str
    signature_url: str | None = None


class RegistryError(RuntimeError):
    """Generic registry error."""


class VersionConstraintError(RegistryError):
    """No version satisfies the requested constraint."""


class IPluginSource(Protocol):
    kind: PluginSourceKind

    async def list_versions(self, plugin_id: str) -> List[str]: ...
    async def fetch_manifest(self, plugin_id: str, version: str) -> bytes: ...
    def to_ref(self, plugin_id: str, version: str) -> PluginRef: ...


_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[\da-zA-Z.-]+))?"
    r"(?:\+[\da-zA-Z.-]+)?$"
)


def _semver_tuple(version: str) -> Tuple[int, int, int, int, str]:
    """Parse semver to a tuple sortable by precedence (release > prerelease)."""
    m = _SEMVER_RE.fullmatch(version)
    if not m:
        raise ValueError(f"Invalid semver: {version!r}")
    major = int(m.group("major"))
    minor = int(m.group("minor"))
    patch = int(m.group("patch"))
    prerelease = m.group("prerelease") or ""
    release_flag = 0 if prerelease == "" else -1
    return (major, minor, patch, release_flag, prerelease)


def _matches_constraint(version: str, constraint: str) -> bool:
    """Return True if version satisfies constraint (`*`, exact, `^`, `~`)."""
    if constraint == "*":
        return True
    if not constraint.startswith(("^", "~")):
        return version == constraint

    op = constraint[0]
    base = constraint[1:]
    try:
        v_tuple = _semver_tuple(version)
        base_tuple = _semver_tuple(base)
    except ValueError:
        return False

    if op == "^":
        major, minor, patch = base_tuple[0], base_tuple[1], base_tuple[2]
        if major > 0:
            upper = (major + 1, 0, 0, -1, "")
        elif minor > 0:
            upper = (0, minor + 1, 0, -1, "")
        else:
            upper = (0, 0, patch + 1, -1, "")
        return base_tuple <= v_tuple < upper

    if op == "~":
        major, minor = base_tuple[0], base_tuple[1]
        upper = (major, minor + 1, 0, -1, "")
        return base_tuple <= v_tuple < upper

    return False


class GitHubReleasesSource:
    """Read plugin versions + manifests from GitHub Releases."""

    kind: PluginSourceKind = PluginSourceKind.GITHUB_RELEASES

    def __init__(self, *, http: httpx.AsyncClient, org: str = "abs-plugins") -> None:
        self._http = http
        self._org = org.rstrip("/")

    async def list_versions(self, plugin_id: str) -> List[str]:
        url = f"https://api.github.com/repos/{self._org}/{plugin_id}/releases"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return [r["tag_name"].lstrip("v") for r in resp.json() if "tag_name" in r]

    async def fetch_manifest(self, plugin_id: str, version: str) -> bytes:
        tag = f"v{version}"
        url = f"https://api.github.com/repos/{self._org}/{plugin_id}/releases/tags/{tag}"
        resp = await self._http.get(url)
        resp.raise_for_status()
        release = resp.json()
        asset = next((a for a in release.get("assets", []) if a["name"] == "manifest.json"), None)
        if asset is None:
            raise RegistryError("manifest.json asset not found in release")
        dl = await self._http.get(asset["browser_download_url"])
        dl.raise_for_status()
        return dl.content

    def to_ref(self, plugin_id: str, version: str) -> PluginRef:
        base = f"https://github.com/{self._org}/{plugin_id}/releases/download/v{version}"
        download_url = f"{base}/manifest.json"
        return PluginRef(
            id=plugin_id,
            version=version,
            source=self.kind,
            download_url=download_url,
            signature_url=f"{download_url}.sig",
        )


class VerdaccioSource:
    """Read plugin versions + manifests from a private Verdaccio npm registry."""

    kind: PluginSourceKind = PluginSourceKind.VERDACCIO

    def __init__(self, *, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")

    async def list_versions(self, plugin_id: str) -> List[str]:
        resp = await self._http.get(f"{self._base}/-/package/{plugin_id}")
        resp.raise_for_status()
        return list((resp.json() or {}).get("versions", {}).keys())

    async def fetch_manifest(self, plugin_id: str, version: str) -> bytes:
        resp = await self._http.get(f"{self._base}/_manifest/{plugin_id}/{version}.json")
        resp.raise_for_status()
        return resp.content

    def to_ref(self, plugin_id: str, version: str) -> PluginRef:
        download_url = f"{self._base}/{plugin_id}/-/{plugin_id}-{version}.tgz"
        return PluginRef(
            id=plugin_id,
            version=version,
            source=self.kind,
            download_url=download_url,
            signature_url=f"{download_url}.sig",
        )


class PluginRegistry:
    """Facade over multiple sources: discover, resolve, fetch, update-check."""

    def __init__(
        self,
        sources: List[IPluginSource],
        *,
        allow_unsigned: bool = False,
    ) -> None:
        self._sources = sources
        self._allow_unsigned = allow_unsigned
        self._source_by_kind: dict[PluginSourceKind, IPluginSource] = {
            src.kind: src for src in sources
        }

    async def discover(self, plugin_id: str) -> List[PluginRef]:
        refs: dict[Tuple[PluginSourceKind, str], PluginRef] = {}
        for src in self._sources:
            try:
                versions = await src.list_versions(plugin_id)
            except Exception:
                continue
            for ver in versions:
                key = (src.kind, ver)
                if key not in refs:
                    refs[key] = src.to_ref(plugin_id, ver)
        return sorted(
            refs.values(),
            key=lambda r: _semver_tuple(r.version),
            reverse=True,
        )

    async def resolve(
        self,
        plugin_id: str,
        *,
        constraint: str = "*",
        prefer_source: PluginSourceKind | None = None,
    ) -> PluginRef:
        refs = await self.discover(plugin_id)
        if prefer_source is not None:
            refs.sort(
                key=lambda r: (1 if r.source == prefer_source else 0, _semver_tuple(r.version)),
                reverse=True,
            )
        for ref in refs:
            if _matches_constraint(ref.version, constraint):
                return ref
        raise VersionConstraintError(
            f"No version of {plugin_id!r} matches constraint {constraint!r}"
        )

    async def fetch_manifest(self, ref: PluginRef) -> PluginManifest:
        src = self._source_by_kind.get(ref.source)
        if src is None:
            raise RegistryError(f"no source registered for kind {ref.source}")
        raw = await src.fetch_manifest(ref.id, ref.version)
        manifest = PluginManifest.model_validate_json(raw)
        if not self._allow_unsigned:
            has_sig = ref.signature_url is not None or manifest.signature is not None
            if not has_sig:
                raise RegistryError("unsigned manifest")
        return manifest

    async def check_for_updates(
        self, installed: dict[str, str]
    ) -> List[Tuple[str, str, str]]:
        out: List[Tuple[str, str, str]] = []
        for pid, cur in installed.items():
            try:
                latest = await self.resolve(pid, constraint="*")
            except VersionConstraintError:
                continue
            if _semver_tuple(latest.version) > _semver_tuple(cur):
                out.append((pid, cur, latest.version))
        return out


__all__ = [
    "GitHubReleasesSource",
    "IPluginSource",
    "PluginRef",
    "PluginRegistry",
    "PluginSourceKind",
    "RegistryError",
    "VerdaccioSource",
    "VersionConstraintError",
    "_matches_constraint",
    "_semver_tuple",
]
