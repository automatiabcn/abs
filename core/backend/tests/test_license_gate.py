"""011 — License/demo gate enforcement testleri (with_hooks içinde)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.licensing import generate_license


@pytest.fixture
def gate_env(monkeypatch, tmp_path: Path):
    """data_dir + cache_dir izole + license_key boş + require_license off (her test override)."""
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "license_key", "")
    monkeypatch.setattr(settings, "mcp_require_license", False)
    monkeypatch.setattr(settings, "hooks_enabled", False)  # nudge interference yok
    return tmp_path


@pytest.fixture
def hooked_tool():
    """with_hooks ile sarılı bir test fn — eldeki middleware patch'ini doğrular."""
    from app.mcp.middleware import with_hooks

    @with_hooks("gate_test_tool")
    async def fn(prompt: str = "x") -> str:
        return f"OK:{prompt}"

    return fn


@pytest.mark.asyncio
async def test_gate_allows_when_require_license_false(gate_env, hooked_tool):
    out = await hooked_tool(prompt="hello")
    assert out == "OK:hello"


@pytest.mark.asyncio
async def test_gate_allows_when_demo_active(gate_env, hooked_tool, monkeypatch):
    from app.config import settings
    from app.licensing.demo import start_demo

    start_demo()
    monkeypatch.setattr(settings, "mcp_require_license", True)
    out = await hooked_tool(prompt="demo-pass")
    assert out == "OK:demo-pass"


@pytest.mark.asyncio
async def test_gate_blocks_when_demo_expired_no_license(
    gate_env, hooked_tool, monkeypatch
):
    import json

    from app.config import settings
    from app.licensing.demo import _state_path

    # Süresi dolmuş demo state yaz
    expired = time.time() - 86400
    _state_path().write_text(
        json.dumps(
            {
                "started_at": expired - 14 * 86400,
                "expires_at": expired,
                "duration_days": 14,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "mcp_require_license", True)
    out = await hooked_tool(prompt="should-block")
    assert out.startswith("[LICENSE REQUIRED]")


@pytest.mark.asyncio
async def test_gate_fails_closed_when_check_errors(gate_env, hooked_tool, monkeypatch):
    """3rd-eye audit — with require_license ON, an error evaluating the gate
    must BLOCK (fail closed), not let the tool run. The old code logged the
    exception and fell through, executing the tool (fail open)."""
    import app.mcp.gate as gate
    from app.config import settings

    def _boom():
        raise RuntimeError("gate DB unavailable")

    monkeypatch.setattr(gate, "_gate_status", _boom)
    monkeypatch.setattr(settings, "mcp_require_license", True)

    out = await hooked_tool(prompt="should-not-run")
    assert out.startswith("[LICENSE REQUIRED]")
    assert "should-not-run" not in out  # tool body never executed


@pytest.mark.asyncio
async def test_gate_allows_when_license_active(gate_env, hooked_tool, monkeypatch):
    from app.config import settings

    token = generate_license("cust_gate", tier="self-host", seat_count=1, valid_days=30)
    monkeypatch.setattr(settings, "license_key", token)
    monkeypatch.setattr(settings, "mcp_require_license", True)
    out = await hooked_tool(prompt="lic")
    assert out == "OK:lic"
