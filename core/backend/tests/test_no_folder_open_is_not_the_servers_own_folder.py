# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""An empty workspace root must not mean "wherever the server happens to be".

The editor sends `vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? ""`.
The `?? ""` is reached whenever somebody opens the editor without a folder —
a fresh install, a window opened on a single file, the state the very first
run is in — and nothing between there and the filesystem treated that empty
string as "no project".

Python resolves "" to the process's working directory. Measured 2026-08-05
against the product's own checkout: `workspace_files("")` returned 200 files
of the server's source. In a customer's container that directory is `/app`.
So a Composer run with no folder open would read the product's own code,
send it to whichever provider the customer configured as the context for
their request, and propose edits against paths inside the server.

Nobody would ask for that, which is the point: the customer did not ask for
anything, they just had no folder open, and an empty string was allowed to
mean a directory.

Two tools took a root with no check — `composer_propose` and
`code_graph_build`. `fullstack_scan` already refused a non-directory, which is
what made the omission easy to miss: one of the three was right.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _server_first():
    # Importing a tool module on its own leaves it partially initialised.
    import app.mcp.server  # noqa: F401


def _text(result) -> str:
    return result if isinstance(result, str) else json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("root", ["", "   ", "relative/path", "."])
async def test_composer_refuses_a_root_that_is_not_an_absolute_directory(root):
    from app.mcp.tools.composer_tools import composer_propose

    out = _text(await composer_propose("tidy up", root))
    assert "error" in out.lower(), (
        f"composer_propose accepted {root!r} as a workspace. An empty or "
        f"relative root resolves to the server's own working directory, so the "
        f"run would read the product's source and propose edits inside it."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("root", ["", "   ", "relative/path", "."])
async def test_the_indexer_refuses_the_same_roots(root):
    from app.mcp.tools.codegraph_tools import code_graph_build

    out = _text(await code_graph_build(root))
    assert "error" in out.lower(), (
        f"code_graph_build accepted {root!r}, which would index the server's "
        f"own directory and then answer blast-radius questions from it"
    )


@pytest.mark.asyncio
async def test_a_real_directory_still_works(tmp_path, monkeypatch):
    """The guard must refuse the empty case without refusing the ordinary one."""
    from app.codegraph import graph as codegraph
    from app.mcp.tools.codegraph_tools import code_graph_build

    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    out = _text(await code_graph_build(str(ws)))
    assert "error" not in out.lower(), out


@pytest.mark.asyncio
async def test_the_refusal_says_what_to_do():
    """A developer who opened the editor on no folder needs the next step.

    "error: invalid path" tells them the product is broken. Naming the missing
    thing tells them it is waiting.
    """
    from app.mcp.tools.composer_tools import composer_propose

    out = _text(await composer_propose("tidy up", "")).lower()
    assert "folder" in out or "project" in out, (
        "the refusal does not mention that a folder needs opening: " + out
    )
