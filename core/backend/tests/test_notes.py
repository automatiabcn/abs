# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Notes companion store — CRUD, search, per-key isolation, MCP registration."""

from __future__ import annotations

import asyncio

import pytest

from app.notes import service as notes


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(notes.settings, "data_dir", str(tmp_path / "data"))
    return tmp_path


def test_save_get_update_delete(isolated):
    saved = notes.save("Design", "cascade failover notes", key="w1", project="p")
    nid = saved["id"]
    got = notes.get(nid, key="w1")
    assert got["title"] == "Design"
    assert got["body"] == "cascade failover notes"

    # Update in place keeps the id + created_at.
    upd = notes.save("Design v2", "more", key="w1", note_id=nid)
    assert upd["id"] == nid
    assert notes.get(nid, key="w1")["title"] == "Design v2"

    assert notes.delete(nid, key="w1") is True
    assert notes.get(nid, key="w1") is None


def test_search_ranks_by_overlap(isolated):
    notes.save("Cascade", "provider failover and circuit breaker", key="w1")
    notes.save("Judge", "ast fingerprint scoring", key="w1")
    hits = notes.search("failover breaker", key="w1")
    assert hits
    assert hits[0]["title"] == "Cascade"


def test_per_key_isolation(isolated):
    notes.save("A", "x", key="w1")
    assert len(notes.list_notes(key="w1")) == 1
    assert notes.list_notes(key="w2") == []  # different workspace/tenant


def test_notes_mcp_tools_registered():
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    for tool in ("note_save", "note_list", "note_get", "note_search", "note_delete"):
        assert tool in names, f"{tool} not registered on /mcp"
