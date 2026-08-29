# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A check that exits 0 and says nothing proved nothing.

Live 2026-08-28: a project's `.venv/bin/python` was a ten-byte stub (an
evicted cloud file). It ran, printed nothing, exited 0 — and the panel
showed "passed" over a test suite that never started. The tool now says
`inconclusive`, and the panel shows "unverified".
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _res(**over):
    base = dict(
        ok=True, exit_code=0, stdout="", stderr="", mechanism="seatbelt",
        duration_ms=5, refused=None, truncated=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_silent_exit_zero_is_inconclusive_and_real_output_is_not(monkeypatch, tmp_path):
    import app.mcp.server  # noqa: F401 — circular import guard
    from app.mcp.tools import sandbox_tools as st

    monkeypatch.setattr(st._sandbox, "run", lambda *a, **k: _res(), raising=True)
    monkeypatch.setattr(st, "_workspace_ok", lambda *a, **k: None, raising=False)
    out = json.loads(await st.sandbox_run("python3 -m pytest -q", workspace_root=str(tmp_path)))
    if "refused" in out and out.get("refused"):
        pytest.skip(f"sandbox refused in this environment: {out['refused']}")
    assert out["ok"] is True
    assert out["inconclusive"] is True

    monkeypatch.setattr(st._sandbox, "run", lambda *a, **k: _res(stdout="3 passed in 0.4s"), raising=True)
    out = json.loads(await st.sandbox_run("python3 -m pytest -q", workspace_root=str(tmp_path)))
    if not out.get("refused"):
        assert out["inconclusive"] is False
