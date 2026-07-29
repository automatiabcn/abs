"""Directed call-graph — build, blast-radius, callers, callees + MCP tools."""

from __future__ import annotations

import asyncio

import pytest

from app.codegraph import graph


def test_codegraph_mcp_tools_registered():
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    for tool in ("code_graph_build", "code_blast_radius", "code_callers", "graph_related"):
        assert tool in names, f"{tool} not registered on /mcp"


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(graph.settings, "data_dir", str(tmp_path / "data"))
    return tmp_path


def test_blast_radius_is_transitive(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "m.py").write_text(
        "def c():\n    return 1\n\n"
        "def b():\n    return c()\n\n"
        "def a():\n    return b()\n",
        encoding="utf-8",
    )
    r = graph.build(str(ws), key="t1")
    assert r["symbols"] >= 3
    assert r["edges"] >= 2

    br = graph.blast_radius("c", key="t1")
    assert br["found"]
    affected = {s["symbol"] for L in br["layers"] for s in L["symbols"]}
    assert "b" in affected  # direct caller
    assert "a" in affected  # transitive caller

    direct = {x["symbol"] for x in graph.callers("c", key="t1")}
    assert direct == {"b"}  # only the direct caller

    out = {x["name"] for x in graph.callees("a", key="t1")}
    assert "b" in out


def test_blast_radius_across_files(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "util.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    (ws / "app.py").write_text(
        "def handler():\n    return helper()\n", encoding="utf-8"
    )
    graph.build(str(ws), key="t2")

    br = graph.blast_radius("helper", key="t2")
    assert br["found"]
    affected = {s["symbol"] for L in br["layers"] for s in L["symbols"]}
    assert "handler" in affected
    assert any(f.endswith("app.py") for f in br["affected_files"])


def test_blast_radius_by_file_path(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "util.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    (ws / "app.py").write_text(
        "def handler():\n    return helper()\n", encoding="utf-8"
    )
    graph.build(str(ws), key="t3")
    br = graph.blast_radius(str(ws / "util.py"), key="t3")
    assert br["found"]
    affected = {s["symbol"] for L in br["layers"] for s in L["symbols"]}
    assert "handler" in affected


def test_missing_symbol_is_not_found(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "m.py").write_text("def only():\n    return 1\n", encoding="utf-8")
    graph.build(str(ws), key="t4")
    br = graph.blast_radius("does_not_exist", key="t4")
    assert br["found"] is False
    assert br["total_affected"] == 0


def test_stats_and_workspace_key(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "m.py").write_text(
        "def c():\n    return 1\n\ndef b():\n    return c()\n", encoding="utf-8"
    )
    key = graph.workspace_key(str(ws))
    graph.build(str(ws), key=key)
    st = graph.stats(key=key)
    assert st["symbols"] >= 2
    assert st["edges"] >= 1
    assert 0 <= st["resolved_pct"] <= 100
