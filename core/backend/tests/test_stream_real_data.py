"""SSE _build_mcp_tools + _build_budget real tracker / workflow_state feed."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_stream_builders_use_real_tracker_and_workflow_stats(
    monkeypatch, tmp_path: Path
):
    """tracker.bump x5 → top tool, workflow_state taze → '0/0 ok'."""
    from app.api import stream as stream_mod
    from app.config import settings
    from app.mcp.tracking import UsageTracker

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    fresh = UsageTracker()
    monkeypatch.setattr(stream_mod, "tracker", fresh)

    for _ in range(5):
        await fresh.bump("ask_test_010")

    mcp_payload = stream_mod._build_mcp_tools()
    assert mcp_payload["tools"], "tracker'da kayıt var ama tools boş"
    assert mcp_payload["tools"][0]["name"] == "ask_test_010"
    assert mcp_payload["tools"][0]["count_24h"] == 5
    assert mcp_payload["total_24h"] == 5

    budget = stream_mod._build_budget()
    assert budget["workflow"]["summary"] == "0/0 ok"
    assert budget["workflow"]["items"] == []


def test_license_status_event_payload(monkeypatch, tmp_path):
    """license-status SSE event payload contract."""
    from app.api import stream as stream_mod
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "license_key", "")
    monkeypatch.setattr(settings, "mcp_require_license", False)

    payload = stream_mod._build_license_status()
    assert "license_active" in payload
    assert "demo_active" in payload
    assert "demo_days_remaining" in payload
    assert "require_license" in payload
    assert "allowed" in payload
    assert payload["purchase_url"].startswith("https://")
    # require_license False → her zaman allowed True
    assert payload["allowed"] is True
