# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/agent/capabilities — the answer, never the setting.

The endpoint's whole job is to be honest about a trust boundary, so what is
tested is that it reports the boundary rather than moving it: it needs an admin,
it says what is off while it is off, it names the folders that were actually
opened, and there is no verb on the router that would let a panel field write
`agent_fs_roots` — that value belongs in .env next to the database password.
"""

from __future__ import annotations

import pytest

from app.api import agent_caps
from app.api.auth import current_admin
from app.config import settings
from app.main import app


@pytest.fixture()
def as_admin():
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@example.com"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_admin, None)


def test_it_needs_an_admin(client):
    assert client.get("/v1/agent/capabilities").status_code in (401, 403)


def test_a_locked_down_install_says_so(client, as_admin, monkeypatch):
    monkeypatch.setattr(settings, "agent_fs_roots", [])
    monkeypatch.setattr(settings, "agent_fs_write_enabled", False)
    monkeypatch.setattr(settings, "agent_shell_enabled", False)

    body = client.get("/v1/agent/capabilities").json()

    assert body["can_read_system"] is True  # facts about this server: always on
    assert body["can_read_files"] is False
    assert body["can_write_files"] is False
    assert body["can_run_commands"] is False
    assert body["file_roots"] == []
    # A capability that is off is not merely refused at call time — its tools
    # are not in the catalogue the model is shown.
    assert not any(tool["name"].startswith("fs_") for tool in body["tools"])


def test_it_names_the_folders_that_were_actually_opened(
    client, as_admin, monkeypatch, tmp_path
):
    real = tmp_path / "docs"
    real.mkdir()
    # The second one is a typo. roots() drops it, so the panel must not show it:
    # an operator reading this page has to see what the agent reaches, not what
    # somebody meant to type.
    monkeypatch.setattr(settings, "agent_fs_roots", [str(real), str(tmp_path / "typo")])

    body = client.get("/v1/agent/capabilities").json()

    assert body["file_roots"] == [str(real)]
    assert body["can_read_files"] is True
    assert {"fs_list", "fs_read", "fs_search"} <= {t["name"] for t in body["tools"]}


def test_writing_is_stated_as_gated_not_implied(client, as_admin):
    body = client.get("/v1/agent/capabilities").json()
    assert body["approval_required_for"] == ["write", "shell"]


def test_the_router_offers_no_way_to_widen_the_boundary():
    # A POST here would be a text field where someone types "/" and reads the
    # host's own secrets back through a chat window.
    methods = {method for route in agent_caps.router.routes for method in route.methods}
    assert methods == {"GET"}
