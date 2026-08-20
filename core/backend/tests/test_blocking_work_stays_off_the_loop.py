"""Blocking work in async tools runs in a thread, and revocation is not a DB
round-trip per keystroke.

Audit 2026-08-18: sandbox_run ran subprocess.run inline (a two-minute test
suite froze Tab and the title bar for everyone), Composer indexed and read
the workspace inline, provider_key_set probed the network inline for up to
8 s, and the MCP middleware asked the database whether the token was
revoked on every request.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "app"


def _src(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def test_sandbox_run_does_not_block_the_loop():
    s = _src("mcp/tools/sandbox_tools.py")
    body = s[s.index("async def sandbox_run("):]
    assert re.search(r"await _asyncio\.to_thread\(\s*_sandbox\.run", body)
    assert "min(max(float(timeout), 1.0), 600.0)" in body


def test_composer_lists_indexes_and_reads_in_a_thread():
    s = _src("composer/runtime.py")
    body = s[s.index("async def run_composer("):]
    assert "await _asyncio.to_thread(workspace_files, workspace_root)" in body
    assert body.count("await _asyncio.to_thread(codegraph.build, workspace_root, key=key)") == 2
    assert "await _asyncio.to_thread(\n                relevant_files," in body
    # no bare synchronous call left in the async body
    assert not re.search(r"^\s+codegraph\.build\(workspace_root, key=key\)", body, re.M)


def test_the_key_probe_runs_in_a_thread():
    s = _src("mcp/tools/engine_panel_tools.py")
    body = s[s.index("async def provider_key_set("):]
    assert "await _asyncio.to_thread(probe_provider_key, provider, value.strip())" in body


def test_revocation_is_cached_and_a_revoke_invalidates_it(monkeypatch):
    from app.api import mcp_tokens as mt

    calls = []

    class _DB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, *a, **k):
            calls.append(1)

            class R:
                @staticmethod
                def first():
                    return None

            return R()

    monkeypatch.setattr(mt, "get_session_sync", lambda: _DB())
    monkeypatch.setattr(mt, "_revoke_cache", {})
    tok = "abs_mcp_x.y"
    assert mt._is_revoked(tok) is False
    assert mt._is_revoked(tok) is False
    assert len(calls) == 1, "the second look-up within the TTL must not hit the DB"
    # a revoke flips the cached answer at once
    import time

    mt._revoke_cache[mt._token_digest(tok)] = (True, time.monotonic())
    assert mt._is_revoked(tok) is True
    assert len(calls) == 1
