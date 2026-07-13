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
    # An "ask" call plus inline analysis: both hooks have something to say, and
    # both get to say it.
    cmd = 'ask "write a python function" gptoss && python3 -c "data=[1,2]; analyze(data); calculate(data)"'
    out = dispatcher.dispatch_hooks("Bash", {"command": cmd})
    ctx = out["additional_context"]
    assert "mcp__abs__qual_code" in ctx  # the feature nudge
    assert "ABS delegation" in ctx  # the delegation nudge


def test_mcp_tool_mcp_nudge_path():
    # The mcp__abs__ prefix is stripped, and ask_gptoss earns the nudge that
    # points at the pipelines that beat a single model.
    out = dispatcher.dispatch_hooks("mcp__abs__ask_gptoss", {"prompt": "x"})
    assert "mcp__abs__race_code" in out["additional_context"]


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
