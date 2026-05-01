"""dispatcher — 5 hook orchestrator + isolation."""

from __future__ import annotations

import pytest

from app.config import settings
from app.hooks import dispatcher


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path / "artifacts"))
    monkeypatch.setattr(settings, "hooks_enabled", True)


def test_disabled_hooks_returns_empty():
    import app.config as cfg

    cfg.settings.hooks_enabled = False
    try:
        out = dispatcher.dispatch_hooks("Bash", {"command": "ls"})
        assert out == {"additional_context": "", "deny_reason": None}
    finally:
        cfg.settings.hooks_enabled = True


def test_bash_delegate_and_feature_nudges_compose():
    # inline python analiz + "ask" keyword'ü birlikte → iki hook da tetiklenir
    cmd = 'ask "python function yaz" gptoss && python3 -c "data=[1,2]; analyze(data); calculate(data)"'
    out = dispatcher.dispatch_hooks("Bash", {"command": cmd})
    ctx = out["additional_context"]
    # En az iki farklı nudge var
    assert "FEATURE NUDGE" in ctx
    assert "DELEGATE NUDGE" in ctx


def test_mcp_tool_mcp_nudge_path():
    out = dispatcher.dispatch_hooks("mcp__abs__ask_gptoss", {"prompt": "x"})
    # mcp__abs__ prefix strip edilir, ask_gptoss için MCP idle nudge
    assert "FEATURE NUDGE" in out["additional_context"]


def test_claude_code_hook_output_shape():
    out = dispatcher.dispatch_hooks("mcp__abs__ask_gptoss", {"prompt": "x"})
    shaped = dispatcher.to_claude_code_hook_output(out)
    assert "hookSpecificOutput" in shaped
    assert shaped["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "additionalContext" in shaped["hookSpecificOutput"]


def test_hook_failure_does_not_break_dispatch(monkeypatch):
    # plan_first hook'unu exception atan bir stub ile değiştir
    def _boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(dispatcher.plan_first, "maybe_plan_first_nudge", _boom)
    out = dispatcher.dispatch_hooks("Bash", {"command": "ls"})
    # safe_hook decorator'ı yutmamış çünkü biz stub attık; dispatcher
    # exception'ı raise etmeli mi, etmemeli mi? Production tasarımında etmemeli;
    # test: dispatch çökmediğini doğrula
    try:
        assert isinstance(out, dict)
    except AssertionError:
        raise
