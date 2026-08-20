# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The Composer has to run on the keys the customer added.

Third time today, and this one is in the feature the product leads with.

`composer_propose` read the caller's tenant and dropped the user — the variable
was literally named `_user` — and `run_composer` was called with `tenant_id`
and no `user_subject`. Keys added from the editor are stored per user
(`owner_type='user'`), so `tenant_configured_providers` found none, and the
chain the Composer built contained only whatever the OPERATOR had configured.

Measured, not reasoned about: on 2026-08-02 an account with five keys ran eight
tasks through the harness and the server log showed one provider attempted —
groq, the operator's — while `capability_status` on the same token reported
five. The customer's keys were invisible to the one feature they bought.

This is the failure `app/providers/byok.py` exists to name: "a path builds its
chain WITHOUT the caller's keys, so an install whose providers are all BYOK
reports that it has none". The judge got this fix on 08-01, `ask_disagree` got
it this morning, and the Composer was still doing it.
"""

from __future__ import annotations

import pytest

import app.mcp.server  # noqa: F401  (registers the tools)
from app.mcp.tools import composer_tools


@pytest.mark.asyncio
async def test_the_tool_passes_the_user_not_only_the_tenant(monkeypatch, tmp_path):
    seen: dict = {}

    async def _fake_run(task, **kwargs):  # noqa: ANN001
        seen.update(kwargs)

        class _Run:
            def model_dump_json(self, **_k):
                return "{}"

        return _Run()

    monkeypatch.setattr("app.composer.run_composer", _fake_run, raising=False)
    monkeypatch.setattr(
        "app.mcp.context.get_mcp_caller", lambda: ("acme", "dev@acme.com"), raising=False
    )

    await composer_tools.composer_propose("do the thing", str(tmp_path))

    assert seen.get("tenant_id") == "acme"
    assert seen.get("user_subject") == "dev@acme.com", (
        "the caller's identity was cut in half, and the half that was dropped "
        "is the one the customer's keys are filed under"
    )


@pytest.mark.asyncio
async def test_an_unknown_caller_still_gets_a_run(monkeypatch, tmp_path):
    """No caller is the operator's own install, not an error."""
    seen: dict = {}

    async def _fake_run(task, **kwargs):  # noqa: ANN001
        seen.update(kwargs)

        class _Run:
            def model_dump_json(self, **_k):
                return "{}"

        return _Run()

    def _boom():
        raise RuntimeError("no context")

    monkeypatch.setattr("app.composer.run_composer", _fake_run, raising=False)
    monkeypatch.setattr("app.mcp.context.get_mcp_caller", _boom, raising=False)

    await composer_tools.composer_propose("task", str(tmp_path))
    assert seen.get("tenant_id"), "the run lost its tenant entirely"
    assert seen.get("user_subject") is None


@pytest.mark.asyncio
async def test_the_graph_key_is_the_project_not_the_person(monkeypatch, tmp_path):
    """The symbol graph is per WORKSPACE, not per person: two developers in one
    tenant looking at the same repo must not each rebuild it.

    This asserted `graph_key == "acme"` — the tenant, spelled out. That was the
    same thing as "the workspace" only for as long as a tenant had one project.
    From 2026-08-03 the graph is keyed per project, because two projects under
    one tenant were answering about each other, and the literal value outlived
    the reasoning it stood for.

    So the property is checked rather than the spelling: the key must not vary
    with the person, and it must vary with the project.
    """
    seen: dict = {}
    keys: list = []

    async def _fake_run(task, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        keys.append(kwargs.get("graph_key"))

        class _Run:
            def model_dump_json(self, **_k):
                return "{}"

        return _Run()

    monkeypatch.setattr("app.composer.run_composer", _fake_run, raising=False)

    monkeypatch.setattr(
        "app.mcp.context.get_mcp_caller", lambda: ("acme", "dev@acme.com"), raising=False
    )
    await composer_tools.composer_propose("task", str(tmp_path))

    # Same tenant, same project, different person.
    monkeypatch.setattr(
        "app.mcp.context.get_mcp_caller",
        lambda: ("acme", "someone-else@acme.com"),
        raising=False,
    )
    await composer_tools.composer_propose("task", str(tmp_path))

    assert keys[0] == keys[1], (
        "the graph key picked up the user, so every person re-indexes the "
        "same workspace"
    )

    # Same tenant, same person, a different project.
    other = tmp_path.parent / (tmp_path.name + "-other")
    other.mkdir()
    await composer_tools.composer_propose("task", str(other))
    assert keys[2] != keys[0], (
        "two projects in one tenant share a graph key, so blast-radius answers "
        "about whichever was indexed last"
    )
