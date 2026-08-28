# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor chat has a voice.

Found 2026-08-28 on screen: the chat's answers were docstrings echoed back
in one block. The question and the files went to the model with no
instruction at all, so the model produced what an uninstructed model
produces — a dump. These tests pin what the chat now sends and, as
important, what it does NOT change for the callers that never asked for a
voice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.chat.prompt import CHAT_INSTRUCTIONS, chat_prompt
from app.workspace import current as ws


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})


def test_instructions_first_question_last():
    """The two ends of the input are where a mid-size model looks; the
    files belong in the middle, the question at the very end."""
    out = chat_prompt(
        "Neden login 500 veriyor?",
        files=[("app/routes.py", "def login():\n    pass\n")],
        project_name="shop",
        history="you: hi\nabs: hello",
    )
    assert out.startswith(CHAT_INSTRUCTIONS.strip()[:40])
    assert out.rstrip().endswith("Neden login 500 veriyor?")
    i_hist = out.index("Conversation so far")
    i_files = out.index("--- app/routes.py ---")
    i_q = out.index("The developer asks:")
    assert i_hist < i_files < i_q
    assert "(shop)" in out


def test_the_voice_rules_are_the_ones_that_were_missing_on_screen():
    """Each rule here answers one thing that was visibly wrong."""
    text = CHAT_INSTRUCTIONS
    assert "Lead with the answer" in text  # was: docstring dump
    assert "Do not repeat the code" in text  # was: file echoed back
    assert "app/routes.py:42" in text  # was: no way to click through
    # Live 08-28: the model copied the placeholder literally ("models.py:LINE").
    assert "never a placeholder" in text and "path/to/file.py:LINE" not in text
    assert "Never invent an API" in text
    assert "language the developer wrote in" in text  # TR/ES/EN developers
    # Live 08-28: "explain every function at length" was refused with "the
    # side panel is narrow". Brevity is the default, not a ceiling.
    assert "length follows the request" in text
    assert "Never refuse or shorten an answer because of the panel" in text


def test_no_files_no_history_is_still_the_voice():
    out = chat_prompt("what is a decorator?")
    assert "Files from the project" not in out
    assert "Conversation so far" not in out
    assert out.rstrip().endswith("what is a decorator?")


@pytest.mark.asyncio
async def test_cascade_ask_in_chat_style_sends_the_voice(tmp_path: Path, monkeypatch):
    import app.mcp.server  # noqa: F401 — circular import guard
    from app.mcp.tools import engine_panel_tools as ept

    root = str(tmp_path.resolve())
    (tmp_path / "billing.py").write_text("def vat(x):\n    return x * 0.21\n")
    seen = {}

    async def fake_cascade(prompt, **kwargs):
        seen["prompt"] = prompt

        class R:
            text = "ok"
            provider = "groq"
            model = "m"
            tokens_in = 1
            tokens_out = 1
            cached = False
            truncated = False

        return R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake_cascade)
    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["groq"], raising=False)

    out = json.loads(
        await ept.cascade_ask(
            "how is vat computed?",
            workspace_root=root,
            use_cache=False,
            style="chat",
            history="you: hi\nabs: hello",
        )
    )
    assert out["ok"] is True
    assert out["used_files"] == ["billing.py"], out
    p = seen["prompt"]
    assert p.startswith("You are ABS"), p[:80]
    assert "--- billing.py ---" in p
    assert p.rstrip().endswith("how is vat computed?")
    assert p.index("Conversation so far") < p.index("--- billing.py ---")


@pytest.mark.asyncio
async def test_without_style_the_prompt_is_the_bare_one(tmp_path: Path, monkeypatch):
    """Inline edit and external MCP clients built on the bare prompt. A
    voice they did not ask for would change every one of their answers."""
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import engine_panel_tools as ept

    root = str(tmp_path.resolve())
    (tmp_path / "billing.py").write_text("def vat(x):\n    return x * 0.21\n")
    seen = {}

    async def fake_cascade(prompt, **kwargs):
        seen["prompt"] = prompt

        class R:
            text = "ok"
            provider = "groq"
            model = "m"
            tokens_in = 1
            tokens_out = 1
            cached = False
            truncated = False

        return R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake_cascade)
    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["groq"], raising=False)

    await ept.cascade_ask("how is vat computed?", workspace_root=root, use_cache=False)
    p = seen["prompt"]
    assert p.startswith("how is vat computed?")
    assert "You are ABS" not in p
    assert "--- billing.py ---" in p
