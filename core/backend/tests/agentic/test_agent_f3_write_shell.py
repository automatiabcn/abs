# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""F3 — the assistant can change things, and cannot do it alone.

The claim under test is not "the write tool is careful". It is structural: a
write or a command *cannot execute* on the model's say-so, because the loop never
calls it — it files an approval, and only the approval path can run it. So the
tests attack the structure. They point a prompt injection at the write tool. They
approve a command and then take the permission away before it runs. They approve
a note in a documents folder and try to land it in ~/.ssh.

If any of these ever goes green the wrong way, the product's central promise is
gone, and it will have gone quietly.
"""

from __future__ import annotations

import json

import pytest

from app.agentic import dispatcher, write_tools
from app.agentic.approvals_bridge import AGENT_TOOL_CHANNEL, payload_of, request_tool_approval
from app.agentic.paths import PathDenied
from app.agentic.policy import Level, check, is_enabled
from app.config import settings


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    (root / "notes.md").write_text("existing", encoding="utf-8")
    (root / ".env").write_text("ABS_GROQ_API_KEY=sk-live", encoding="utf-8")

    monkeypatch.setattr(settings, "agent_fs_roots", [str(root)])
    monkeypatch.setattr(settings, "agent_fs_write_enabled", True)
    monkeypatch.setattr(settings, "agent_shell_enabled", True)
    return {"root": root, "tmp": tmp_path}


# --- the switches ------------------------------------------------------------


class TestTheseToolsAreOffUntilTheyAreOn:
    def test_writing_is_absent_from_the_catalogue_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_fs_write_enabled", False)
        monkeypatch.setattr(settings, "agent_shell_enabled", False)
        names = {tool.name for tool in dispatcher.catalogue()}
        assert "fs_write" not in names and "run_command" not in names
        # Not "listed and refused": a model cannot be argued into calling a tool
        # it was never told exists.
        assert "fs_write" not in dispatcher.describe_for_prompt()

    def test_letting_it_write_files_does_not_let_it_run_commands(self, workspace, monkeypatch):
        monkeypatch.setattr(settings, "agent_shell_enabled", False)
        names = {tool.name for tool in dispatcher.catalogue()}
        assert "fs_write" in names
        assert "run_command" not in names

    def test_both_switches_on_still_means_every_call_needs_a_person(self, workspace):
        assert check(Level.WRITE).verdict == "approve"
        assert check(Level.SHELL).verdict == "approve"
        assert is_enabled(Level.WRITE) and is_enabled(Level.SHELL)


# --- the boundary still holds behind the approval ----------------------------


class TestAnApprovedWriteIsStillNotAnywhere:
    @pytest.mark.asyncio
    async def test_it_writes_inside_the_allowed_folder(self, workspace):
        target = workspace["root"] / "draft.md"
        out = await write_tools.fs_write(str(target), "the draft")
        assert target.read_text(encoding="utf-8") == "the draft"
        assert "Created" in out

    @pytest.mark.asyncio
    async def test_approving_a_note_is_not_a_way_into_dot_ssh(self, workspace):
        # "I approved a file in my documents folder" must not put bytes in a
        # place the operator never opened up.
        outside = workspace["tmp"] / ".ssh" / "authorized_keys"
        with pytest.raises(PathDenied, match="outside"):
            await write_tools.fs_write(str(outside), "ssh-rsa AAAA...")

    @pytest.mark.asyncio
    async def test_it_will_not_overwrite_a_secret_inside_an_allowed_folder(self, workspace):
        with pytest.raises(PathDenied, match="not readable"):
            await write_tools.fs_write(str(workspace["root"] / ".env"), "ABS_GROQ_API_KEY=stolen")
        assert "sk-live" in (workspace["root"] / ".env").read_text(encoding="utf-8")


class TestAnApprovedCommandRunsWhatWasRead:
    @pytest.mark.asyncio
    async def test_it_runs_and_reports_the_output(self, workspace):
        out = await write_tools.run_command("echo hello")
        assert "hello" in out
        assert "finished" in out

    @pytest.mark.asyncio
    async def test_a_failing_command_is_an_outcome_not_an_outage(self, workspace):
        out = await write_tools.run_command("exit 3")
        assert "exited with code 3" in out

    @pytest.mark.asyncio
    async def test_the_server_keys_are_not_in_the_environment_it_inherits(
        self, workspace, monkeypatch
    ):
        # Otherwise `echo $ABS_GROQ_API_KEY`, wrapped in something that looks
        # harmless enough to approve, prints the server's credentials into a
        # transcript that gets stored and indexed.
        monkeypatch.setenv("ABS_GROQ_API_KEY", "sk-live-secret-value")
        monkeypatch.setenv("HOME_LOOKING_VAR", "harmless")
        out = await write_tools.run_command("echo [$ABS_GROQ_API_KEY] [$HOME_LOOKING_VAR]")
        assert "sk-live-secret-value" not in out
        assert "harmless" in out  # ordinary variables still come through

    @pytest.mark.asyncio
    async def test_a_command_that_never_finishes_is_stopped(self, workspace, monkeypatch):
        monkeypatch.setattr(write_tools, "SHELL_TIMEOUT_SECONDS", 0.5)
        with pytest.raises(PathDenied, match="stopped"):
            await write_tools.run_command("sleep 5")


# --- the approval itself -----------------------------------------------------


class TestTheApprovalCarriesTheCall:
    def test_the_stored_payload_is_the_call_not_the_summary(self, workspace, monkeypatch, tmp_path):
        opened = {}

        class FakeItem:
            channel = AGENT_TOOL_CHANNEL
            proposed_message = json.dumps(
                {"name": "run_command", "args": {"command": "ls -la"}}
            )

        call = payload_of(FakeItem())
        assert call == {"name": "run_command", "args": {"command": "ls -la"}}
        assert opened == {}

    def test_something_that_is_not_a_tool_call_reads_as_none(self):
        class Outbound:
            channel = "email"
            proposed_message = "Dear Falcon, ..."

        assert payload_of(Outbound()) is None

    def test_a_corrupt_payload_reads_as_none_rather_than_running_something(self):
        class Corrupt:
            channel = AGENT_TOOL_CHANNEL
            proposed_message = "{not json"

        assert payload_of(Corrupt()) is None


class TestTheAssistantCanAskAndOnlyAsk:
    @pytest.mark.asyncio
    async def test_a_write_the_model_wants_becomes_a_pending_approval_and_not_a_write(
        self, workspace, monkeypatch
    ):
        """The whole of F3 in one test.

        The model asks to write. The write does not happen. An approval appears
        in the queue, carrying the exact call — so a person can look at it, and
        so the only path to execution runs through them.
        """
        from app.agentic import loop as loop_mod
        from app.approvals.service import list_approvals

        target = workspace["root"] / "summary.md"
        replies = iter(
            [
                json.dumps(
                    {
                        "action": "tool",
                        "name": "fs_write",
                        "arguments": {"path": str(target), "content": "the summary"},
                    }
                ),
                json.dumps({"action": "final", "answer": "I asked to save it; it needs your ok."}),
            ]
        )

        async def fake_ask(prompt, providers, max_tokens, tenant, user_subject):
            return next(replies)

        monkeypatch.setattr(loop_mod, "_ask", fake_ask)

        events = [
            event
            async for event in loop_mod.run_agent_loop(
                user_message="Save a summary of this to summary.md",
                providers=["groq"],
                tenant="default",
                requester="admin@local",
            )
        ]

        kinds = [event.type for event in events]
        assert "approval-required" in kinds
        assert "tool-result" not in kinds  # nothing ran
        assert not target.exists()  # and nothing was written

        approval = next(e for e in events if e.type == "approval-required")
        approval_id = approval.data["approval_id"]
        assert approval_id is not None

        # It is in the operator's queue, and it carries the call verbatim —
        # not a paraphrase of it.
        pending = list_approvals(tenant_slug="default", status="pending")
        rows = pending["items"] if isinstance(pending, dict) else pending
        mine = next(r for r in rows if r["id"] == approval_id)
        assert json.loads(mine["proposed_message"]) == {
            "name": "fs_write",
            "args": {"path": str(target), "content": "the summary"},
        }


class TestExecutionReChecksTheGate:
    def test_permission_taken_away_after_approval_blocks_the_run(
        self, workspace, monkeypatch, tmp_path
    ):
        # The operator approved a command, then turned shell off. The approval is
        # not a key to a door that has since been locked.
        from app.actions.executor import _execute_agent_tool

        marker = tmp_path / "should-not-exist"

        class Item:
            id = 1
            agent_id = "assistant"
            channel = AGENT_TOOL_CHANNEL
            target_company = ""
            proposed_message = json.dumps(
                {"name": "run_command", "args": {"command": f"touch {marker}"}}
            )

        monkeypatch.setattr(settings, "agent_shell_enabled", False)

        out = _execute_agent_tool(
            Item(),
            tenant="default",
            base={
                "tenant_slug": "default",
                "approval_item_id": 1,
                "agent_id": "assistant",
                "target_company": "",
                "message": "",
            },
        )

        assert out["status"] == "blocked"
        assert not marker.exists()  # the command did not run

    def test_an_approved_command_actually_runs(self, workspace, monkeypatch, tmp_path):
        from app.actions.executor import _execute_agent_tool

        marker = workspace["root"] / "it-ran.txt"

        class Item:
            id = 2
            agent_id = "assistant"
            channel = AGENT_TOOL_CHANNEL
            target_company = ""
            proposed_message = json.dumps(
                {"name": "run_command", "args": {"command": f"echo done > {marker}"}}
            )

        out = _execute_agent_tool(
            Item(),
            tenant="default",
            base={
                "tenant_slug": "default",
                "approval_item_id": 2,
                "agent_id": "assistant",
                "target_company": "",
                "message": "",
            },
        )

        assert out["status"] == "executed"
        assert marker.exists()
