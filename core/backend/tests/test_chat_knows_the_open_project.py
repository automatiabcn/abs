# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Opening a project has to change what the product knows.

The first feedback from a real install (2026-08-03): a provider was connected,
a project was open, and the chat answered as though the repository did not
exist. It did not — as far as that tool was concerned. Of the thirty-three
tools the editor calls, exactly one sent the workspace, so opening a project
made Composer project-aware and left everything else answering from general
knowledge.

The founder's rule after that: as soon as a project is open, every capability
works against it.

The repair is not thirty-three new arguments — that leaves the thirty-fourth
tool wrong again the day it is written. The editor states the workspace once
via `workspace_set`, and any tool that wants it asks. These tests pin the two
halves that have to hold: the server remembers what it was told, and the chat
actually uses it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "billing.py").write_text(
        "def compute_invoice_total(items, vat_rate=0.21):\n"
        '    """Invoice total with Catalan VAT."""\n'
        "    return round(sum(i.price * i.qty for i in items) * (1 + vat_rate), 2)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Ledger\nInvoicing for small studios. VAT lives in src/billing.py.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_server_remembers_which_project_is_open(project: Path):
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "u")
    assert current_workspace("t", "u") is None, "started with a workspace it was never told"

    set_workspace("t", "u", str(project))
    assert current_workspace("t", "u") == str(project.resolve())


def test_one_caller_cannot_see_another_callers_project(project: Path):
    """Two developers on one server are two workspaces, not one.

    A shared answer here would send one customer's file paths — and with the
    chat change, their file *contents* — to another.
    """
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "a")
    forget("t", "b")
    set_workspace("t", "a", str(project))
    assert current_workspace("t", "b") is None


def test_a_path_the_server_cannot_see_is_refused(tmp_path: Path):
    """The editor runs on the laptop; the server may be in a container.

    Storing a root that does not resolve would make every tool that trusts it
    quietly answer about nothing, which is harder to notice than an error.
    """
    from app.workspace.current import current_workspace, forget, set_workspace

    forget("t", "u")
    assert set_workspace("t", "u", str(tmp_path / "not-there")) is None
    assert current_workspace("t", "u") is None


def test_clearing_is_possible(project: Path):
    """"No folder open" is a state the editor has to be able to state."""
    from app.workspace.current import current_workspace, set_workspace

    set_workspace("t", "u", str(project))
    set_workspace("t", "u", "")
    assert current_workspace("t", "u") is None


def test_the_chat_retrieves_from_the_open_project(project: Path):
    """The reported bug, at the level where it was wrong.

    Composer's own retrieval is used on purpose: two implementations of "which
    files matter" drift, and the developer would get different context from the
    chat and the Composer for the same question.
    """
    from app.composer.runtime import relevant_files, workspace_files

    files = workspace_files(str(project))
    assert "src/billing.py" in files

    picked = relevant_files(
        str(project), "How is VAT calculated in this project?", files
    )
    assert picked, "retrieval found nothing in a two-file project"
    names = [rel for rel, _ in picked]
    assert "src/billing.py" in names
    body = dict(picked)["src/billing.py"]
    assert "vat_rate" in body, "the file was named but its contents were not read"


@pytest.mark.asyncio
async def test_workspace_set_reports_a_root_it_cannot_see(tmp_path: Path):
    """The customer has to be told, not left with a chat that stays generic.

    A server in a container cannot see the laptop's paths. Answering "ok" there
    would leave the developer wondering why nothing improved.
    """
    import app.mcp.server  # noqa: F401 — importing a tool module first is a
    # circular import; the server package has to be initialised before it.
    from app.mcp.tools.engine_panel_tools import workspace_set

    out = json.loads(await workspace_set(str(tmp_path / "nope")))
    assert out["ok"] is False
    assert out["error"] == "not_a_directory"
    assert "mounted" in out["detail"], "the message does not say what to do about it"


def test_the_chat_says_which_files_it_sent():
    """The panel's promise: a developer knows what they just sent.

    Context gathered silently breaks that more quietly than not gathering it,
    so the tool returns the list and the panel can show it.
    """
    import inspect

    import app.mcp.server  # noqa: F401 — see above.
    from app.mcp.tools import engine_panel_tools

    src = inspect.getsource(engine_panel_tools.cascade_ask)
    assert '"used_files"' in src, "the answer does not say which files went with it"
