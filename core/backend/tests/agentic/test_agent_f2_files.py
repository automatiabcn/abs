# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""F2 file access — the boundary, attacked.

The happy path is one line and it is not what these tests are for. What is
tested is every way a path can be made to look like it is inside the allowed
folder while landing outside it, plus the case where the folder is legitimately
allowed and the file inside it still must not be read.

The `/data` → `/data-archived` case is not hypothetical: that exact bug shipped
in Anthropic's own filesystem MCP server, because the check was a string prefix
and `"/data-archived".startswith("/data")` is true. It is the first test here.
"""

from __future__ import annotations

import os

import pytest

from app.agentic import dispatcher, fs_tools
from app.agentic.paths import PathDenied, resolve
from app.agentic.policy import Level, is_enabled
from app.config import settings


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An allowed root, a sibling that must stay unreachable, and a secret."""
    root = tmp_path / "data"
    root.mkdir()
    (root / "notes.md").write_text(
        "The Q3 plan is to double revenue.", encoding="utf-8"
    )
    (root / "contract.txt").write_text(
        "Party A agrees to pay Party B.", encoding="utf-8"
    )
    (root / ".env").write_text("ABS_GROQ_API_KEY=sk-live-secret", encoding="utf-8")
    (root / "private.pem").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    sub = root / "vault"
    sub.mkdir()
    (sub / "keys.txt").write_text("master key", encoding="utf-8")

    # The neighbour whose name starts with the root's name. The bug lives here.
    sibling = tmp_path / "data-archived"
    sibling.mkdir()
    (sibling / "old.md").write_text("last year's numbers", encoding="utf-8")

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "passwd.txt").write_text("root:x:0:0", encoding="utf-8")

    monkeypatch.setattr(settings, "agent_fs_roots", [str(root)])
    return {"root": root, "sibling": sibling, "outside": outside, "tmp": tmp_path}


class TestBoundary:
    def test_a_sibling_folder_sharing_the_prefix_is_not_inside(self, workspace):
        # /data does not admit /data-archived. Segment comparison, not
        # startswith — the whole reason paths.py exists.
        with pytest.raises(PathDenied, match="outside"):
            resolve(str(workspace["sibling"] / "old.md"))

    def test_dot_dot_cannot_climb_out(self, workspace):
        escape = str(workspace["root"] / ".." / "elsewhere" / "passwd.txt")
        with pytest.raises(PathDenied, match="outside"):
            resolve(escape)

    def test_a_symlink_pointing_out_is_followed_before_it_is_judged(self, workspace):
        # The classic: the link *is* inside the root, so a check on the string
        # passes. Resolve first, then decide.
        link = workspace["root"] / "shortcut"
        os.symlink(workspace["outside"], link)
        with pytest.raises(PathDenied, match="outside"):
            resolve(str(link / "passwd.txt"))

    def test_an_absolute_path_elsewhere_is_refused(self, workspace):
        with pytest.raises(PathDenied, match="outside"):
            resolve("/etc/passwd")

    def test_no_roots_configured_means_no_file_access_at_all(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_fs_roots", [])
        with pytest.raises(PathDenied, match="not enabled"):
            resolve("/anything")

    def test_a_root_that_does_not_exist_is_dropped_not_trusted(
        self, monkeypatch, tmp_path
    ):
        # A typo in settings must narrow what the agent reaches, never widen it.
        monkeypatch.setattr(settings, "agent_fs_roots", [str(tmp_path / "nope")])
        with pytest.raises(PathDenied, match="not enabled"):
            resolve(str(tmp_path / "nope" / "x.md"))


class TestSecretsInsideAnAllowedRoot:
    def test_dotenv_is_refused_even_though_the_folder_is_allowed(self, workspace):
        # The root is legitimate; the file is not something to read back into a
        # transcript that gets stored and indexed.
        with pytest.raises(PathDenied, match="not readable"):
            resolve(str(workspace["root"] / ".env"))

    def test_key_material_is_refused_by_suffix(self, workspace):
        with pytest.raises(PathDenied, match="not readable"):
            resolve(str(workspace["root"] / "private.pem"))

    def test_a_denied_directory_is_refused_at_any_depth(self, workspace):
        with pytest.raises(PathDenied, match="not readable"):
            resolve(str(workspace["root"] / "vault" / "keys.txt"))

    @pytest.mark.asyncio
    async def test_a_listing_does_not_even_mention_the_secret(self, workspace):
        # Naming it — even to refuse it — tells the model a .env is there and
        # invites a second attempt with a cleverer path.
        out = await fs_tools.fs_list(str(workspace["root"]))
        assert "notes.md" in out
        assert ".env" not in out
        assert "private.pem" not in out
        assert "vault" not in out


class TestTools:
    @pytest.mark.asyncio
    async def test_listing_with_no_path_answers_where_am_i_allowed(self, workspace):
        out = await fs_tools.fs_list()
        assert str(workspace["root"]) in out

    @pytest.mark.asyncio
    async def test_read_returns_the_file(self, workspace):
        out = await fs_tools.fs_read(str(workspace["root"] / "notes.md"))
        assert "double revenue" in out

    @pytest.mark.asyncio
    async def test_read_refuses_a_path_outside(self, workspace):
        with pytest.raises(PathDenied):
            await fs_tools.fs_read(str(workspace["outside"] / "passwd.txt"))

    @pytest.mark.asyncio
    async def test_read_refuses_a_file_too_large_to_be_a_document(
        self, workspace, monkeypatch
    ):
        big = workspace["root"] / "dump.log"
        big.write_text("x" * 2000, encoding="utf-8")
        monkeypatch.setattr("app.agentic.paths.MAX_FILE_BYTES", 1000)
        with pytest.raises(PathDenied, match="KB"):
            await fs_tools.fs_read(str(big))

    @pytest.mark.asyncio
    async def test_read_says_binary_is_binary_rather_than_hallucinating_over_it(
        self, workspace
    ):
        # errors="replace" would hand the model a page of U+FFFD and let it
        # invent meaning in the noise.
        blob = workspace["root"] / "image.md"  # allowed suffix, binary content
        blob.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01")
        with pytest.raises(PathDenied, match="binary"):
            await fs_tools.fs_read(str(blob))

    @pytest.mark.asyncio
    async def test_search_locates_files_without_quoting_them(self, workspace):
        # A search that returned surrounding text would be a way to read a file
        # one grep at a time, with none of fs_read's limits applying.
        out = await fs_tools.fs_search("revenue")
        assert "notes.md" in out
        assert "double revenue" not in out

    @pytest.mark.asyncio
    async def test_search_never_reaches_a_denied_file(self, workspace):
        out = await fs_tools.fs_search("sk-live-secret")
        assert "No file" in out
        assert ".env" not in out


class TestCatalogueWiring:
    def test_file_tools_are_absent_until_a_root_is_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_fs_roots", [])
        assert is_enabled(Level.READ_FILE) is False
        names = {tool.name for tool in dispatcher.catalogue()}
        assert not ({"fs_read", "fs_list", "fs_search"} & names)
        assert "fs_read" not in dispatcher.describe_for_prompt()

    def test_file_tools_appear_once_a_root_is_configured(self, workspace):
        names = {tool.name for tool in dispatcher.catalogue()}
        assert {"fs_read", "fs_list", "fs_search"} <= names

    def test_reading_a_file_still_needs_no_approval(self, workspace):
        # Reading is L1: allowed and audited, not gated. Writing is what stops
        # for a person — and there is still no write tool.
        from app.agentic.policy import check

        assert check(Level.READ_FILE).verdict == "allow"
        assert all(tool.level is not Level.WRITE for tool in dispatcher.catalogue())

    @pytest.mark.asyncio
    async def test_the_dispatcher_runs_a_file_tool_end_to_end(self, workspace):
        out = await dispatcher.run(
            "fs_read", {"path": str(workspace["root"] / "contract.txt")}
        )
        assert "Party A" in out
