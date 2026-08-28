"""Blast radius counts references, not only calls.

Live, 2026-08-28 (G13): `test_client` — a pytest fixture used by five tests
in the same file — answered `total_affected: 0`, and the commit message
would have said "nothing else refers to what changed". Only `Call` nodes
made edges; a fixture arrives as a parameter, and a callback is passed as a
value. Both are dependencies that break when the target changes.
"""

from __future__ import annotations

import pytest

from app.codegraph import graph
from app.symbols.parser import parse_python_file


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(graph.settings, "data_dir", str(tmp_path / "data"))
    return tmp_path


def test_parser_records_parameters_and_name_loads_as_dependencies(tmp_path):
    f = tmp_path / "t.py"
    f.write_text(
        "def test_client():\n    return 1\n\n"
        "def notify():\n    pass\n\n"
        "def test_a(test_client):\n    assert test_client.get('/') == 1\n\n"
        "def test_unused(test_client):\n    pass\n\n"
        "def run(cb=None):\n    schedule(on_done=notify)\n",
        encoding="utf-8",
    )
    syms = {s.name: s for s in parse_python_file(f, roots=[tmp_path])}
    assert "test_client" in syms["test_a"].edges_out
    # a fixture the test only declares (autouse-style) is still a dependency
    assert "test_client" in syms["test_unused"].edges_out
    assert "notify" in syms["run"].edges_out
    # builtins and the function's own name are not dependencies
    assert "len" not in syms["test_a"].edges_out
    assert "run" not in syms["run"].edges_out


def test_blast_radius_reaches_a_fixture_through_its_parameter(isolated_data_dir):
    ws = isolated_data_dir / "ws"
    ws.mkdir()
    (ws / "test_market.py").write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='module')\n"
        "def test_client():\n    return object()\n\n"
        "def test_one(test_client):\n    assert test_client\n\n"
        "def test_two(test_client):\n    assert test_client\n\n"
        "def test_three(test_client):\n    assert test_client\n\n"
        "def test_four(test_client):\n    pass\n",
        encoding="utf-8",
    )
    r = graph.build(str(ws), key="refs")
    assert r["symbols"] >= 4
    br = graph.blast_radius("test_client", key="refs")
    assert br["found"] and br["indexed"]
    assert br["total_affected"] == 4, br
    assert br["affected_files"], br
