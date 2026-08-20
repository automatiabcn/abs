"""Where a project may be — one rule, five doors.

Audit 2026-08-18: composer_propose, code_graph_build, workspace_set,
rag_index and sandbox_run each accepted any absolute directory the server
could see. sandbox_run with workspace_root pointed at the server's own state
directory returned `.env` — session secret included — in stdout.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.workspace import current as ws
from app.workspace import roots


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})
    monkeypatch.delenv("ABS_WORKSPACE_ROOTS", raising=False)


@pytest.mark.parametrize("bad", ["/", "/etc", "/private/etc", "/usr/lib", "/System", "/var", "/tmp"])
def test_system_directories_are_never_projects(bad):
    if not os.path.isdir(bad):
        pytest.skip(f"{bad} not on this machine")
    assert roots.forbidden_reason(bad)


def test_the_home_directory_itself_is_not_a_project():
    assert roots.forbidden_reason(os.path.expanduser("~"))


def test_a_folder_inside_home_is_fine(tmp_path):
    # tmp_path is under /private/var/folders on macOS — a real user location.
    assert roots.forbidden_reason(str(tmp_path)) is None


def test_the_servers_own_state_directory_is_refused(monkeypatch, tmp_path):
    state = tmp_path / "state"
    (state / "data").mkdir(parents=True)
    (state / ".env").write_text("ABS_SESSION_SECRET=x\n")
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(state / "data"), raising=False)
    assert roots.forbidden_reason(str(state / "data"))
    assert roots.forbidden_reason(str(state))  # the parent holding .env, too
    other = tmp_path / "proj"
    other.mkdir()
    assert roots.forbidden_reason(str(other)) is None


def test_configured_roots_confine_every_tenant(monkeypatch, tmp_path):
    (tmp_path / "mounts" / "acme").mkdir(parents=True)
    (tmp_path / "mounts" / "globex").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv("ABS_WORKSPACE_ROOTS", str(tmp_path / "mounts" / "{tenant}"))
    assert roots.forbidden_reason(str(tmp_path / "mounts" / "acme"), "acme") is None
    assert roots.forbidden_reason(str(tmp_path / "mounts" / "globex"), "acme")
    assert roots.forbidden_reason(str(tmp_path / "elsewhere"), "acme")


def test_within_follows_symlinks_out(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    outside = tmp_path / "o"
    outside.mkdir()
    (outside / "secret").write_text("x")
    os.symlink(outside / "secret", proj / "link")
    assert roots.within(str(proj / "a.py"), str(proj))
    assert not roots.within(str(proj / "link"), str(proj))
    assert not roots.within(str(proj / ".." / "o" / "secret"), str(proj))


# --- the doors -------------------------------------------------------------

def test_workspace_set_refuses_a_forbidden_root(monkeypatch, tmp_path):
    state = tmp_path / "state" / "data"
    state.mkdir(parents=True)
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(state), raising=False)
    assert ws.set_workspace("t", "u", str(state), client_id="w") is None
    assert ws.current_workspace("t", "u", client_id="w", explicit_root=str(state)) is None
    assert ws.problem_with_root(str(state)) and "server's own" in ws.problem_with_root(str(state))


@pytest.mark.asyncio
async def test_sandbox_run_refuses_the_servers_state(monkeypatch, tmp_path):
    import json

    import app.mcp.server  # noqa: F401 — circular import guard
    from app.mcp.tools import sandbox_tools as st

    state = tmp_path / "state" / "data"
    state.mkdir(parents=True)
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(state), raising=False)
    called = {}
    monkeypatch.setattr(st._sandbox, "run", lambda *a, **k: called.setdefault("ran", True))
    out = json.loads(await st.sandbox_run("pytest -q", workspace_root=str(state)))
    assert out["ok"] is False and "server's own" in out["refused"]
    assert "ran" not in called


@pytest.mark.asyncio
async def test_rag_index_refuses_a_system_tree(monkeypatch):
    import json

    import app.mcp.server  # noqa: F401
    from app.mcp.tools import rag as rt

    monkeypatch.setattr(rt, "_index_path", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not index")))
    out = json.loads(await rt.rag_index("/etc"))
    assert "error" in out and out["indexed"] == 0


def test_composer_does_not_read_a_file_outside_the_project(tmp_path, monkeypatch):
    """The model named ../secret.txt; the file is not read, the edit is not
    proposed, and the refusal says so. a.py next to it is still proposed."""
    import asyncio

    from app.composer import runtime as composer

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\n")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP\n")

    async def _fake(*a, **k):
        return (
            {"edits": [
                {"path": "../secret.txt", "new_content": "gone\n"},
                {"path": "a.py", "new_content": "x = 2\n"},
            ]},
            ["groq"],
            {"provider": "groq"},
        )

    monkeypatch.setattr(composer, "_generate_edits", _fake)

    async def _judge(diff, path=None, **_c):
        return {"combined_score": 9.0, "llm_score": 9.0, "ast_score": None, "teaching": []}

    monkeypatch.setattr(composer, "judge_diff", _judge)

    opened = []
    real_open = open

    def spy(path, *a, **k):
        opened.append(os.path.realpath(str(path)) if isinstance(path, (str, os.PathLike)) else str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", spy)
    run = asyncio.run(composer.run_composer("edit", workspace_root=str(proj), tenant_id="t", graph_key="t"))
    assert [e.path for e in run.edits] == ["a.py"], run.edits
    assert any("outside the open project" in r for r in run.refused), run.refused
    assert not any(p == os.path.realpath(str(secret)) for p in opened), "secret.txt was opened"


def test_sensitive_read_paths_only_lists_what_exists():
    from app.sandbox import runner

    for p in runner.sensitive_read_paths():
        assert os.path.exists(p)
        assert os.path.isabs(p)


def test_seatbelt_profile_denies_credential_stores(monkeypatch, tmp_path):
    from app.sandbox import runner

    fake_ssh = tmp_path / ".ssh"
    fake_ssh.mkdir()
    monkeypatch.setattr(runner, "sensitive_read_paths", lambda: [str(fake_ssh)])
    prof = runner._seatbelt_profile(str(tmp_path / "ws"), False) if hasattr(runner, "_seatbelt_profile") else None
    if prof is None:
        pytest.skip("no seatbelt profile builder under that name")
    assert "(allow file-read*)" in prof
    assert f'(deny file-read* (subpath "{fake_ssh}"))' in prof
    # order matters: the deny comes after the broad allow (later rules win)
    assert prof.index("(allow file-read*)") < prof.index("(deny file-read*")
