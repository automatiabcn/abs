# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What the developer names goes first; what the project rules say goes
before everything else of theirs; what must not leave, does not — even
when named."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.chat.context import pinned_files, project_rules
from app.chat.prompt import chat_prompt
from app.workspace import current as ws


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text("def market():\n    return 'm'\n")
    (tmp_path / "app" / "billing.py").write_text("def vat(x):\n    return x * 0.21\n")
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_secret\n")
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / "AGENTS.md").write_text("Always answer in Turkish.\nNever touch migrations.\n")
    return tmp_path


def test_named_files_are_read_and_secrets_are_refused(project: Path):
    files, refused = pinned_files(str(project), ["app/routes.py", ".env", "../etc/passwd", "nope.py"])
    assert [rel for rel, _ in files] == ["app/routes.py"]
    assert any(r.startswith(".env:") for r in refused)
    assert any("outside the project" in r for r in refused)
    assert any(r.startswith("nope.py:") for r in refused)


def test_rules_file_is_found_and_capped(project: Path):
    text, where = project_rules(str(project))
    assert where == "AGENTS.md"
    assert "Always answer in Turkish." in text
    (project / ".abs").mkdir()
    (project / ".abs" / "rules.md").write_text("x" * 5000)
    text, where = project_rules(str(project))
    assert where == ".abs/rules.md"
    assert text.endswith("[... rules file truncated ...]")


def test_rules_sit_before_history_and_attachments_before_the_question():
    out = chat_prompt(
        "why?",
        history="Developer: hi",
        rules="Be brief.",
        rules_from="AGENTS.md",
        attachments="--- git diff ---\n+x",
    )
    assert out.index("Project rules (from AGENTS.md)") < out.index("Conversation so far")
    assert out.index("Attached by the developer") < out.index("The developer asks")
    assert out.rstrip().endswith("why?")


def test_prepare_puts_pinned_first_and_reports_the_refused(project: Path, monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import engine_panel_tools as ept

    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["groq"], raising=False)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **k: ["groq"])
    prepared = ept.prepare_chat_ask(
        "how is vat computed?",
        workspace_root=str(project),
        style="chat",
        pinned_files=["app/routes.py", ".env"],
        attachments="+ a line",
    )
    assert "error" not in prepared
    assert prepared["used_files"][0] == "app/routes.py", prepared["used_files"]
    assert "app/billing.py" in prepared["used_files"]  # retrieval still fills the rest
    assert prepared["refused_files"] and prepared["refused_files"][0].startswith(".env:")
    assert prepared["rules_from"] == "AGENTS.md"
    p = prepared["asked"]
    assert "Always answer in Turkish." in p
    assert "gsk_secret" not in p
    assert p.index("--- app/routes.py ---") < p.index("--- app/billing.py ---")
    assert "Attached by the developer:\n+ a line" in p
