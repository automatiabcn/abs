"""Hooks must not log a failure on every tool call because `/app` is not there.

Live, 2026-08-28 (G2): on a developer machine `settings.cache_dir` kept its
container default, `/app/data/cache`; each MCP CallToolRequest logged
`hook delegate_nudge failed: [Errno 30] Read-only file system: '/app'`. The
cache now falls back to the data directory when the configured one cannot
be created.
"""

from __future__ import annotations

from pathlib import Path

from app.hooks import common


def test_cache_path_falls_back_to_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(common.settings, "cache_dir", "/nonexistent-root-zz/cache", raising=False)
    monkeypatch.setattr(common.settings, "data_dir", str(tmp_path / "data"), raising=False)
    p = common.cache_path("delegate_nudge_rate.json")
    assert p == tmp_path / "data" / "cache" / "delegate_nudge_rate.json"
    assert p.parent.is_dir()


def test_cache_path_uses_configured_dir_when_writable(tmp_path, monkeypatch):
    monkeypatch.setattr(common.settings, "cache_dir", str(tmp_path / "cache"), raising=False)
    monkeypatch.setattr(common.settings, "data_dir", str(tmp_path / "data"), raising=False)
    p = common.cache_path("x.json")
    assert p == tmp_path / "cache" / "x.json"
    assert Path(p).parent.is_dir()
