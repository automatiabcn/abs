"""MCP server ships delegation instructions over `initialize`.

Connecting clients (Claude Code, Codex, …) receive `instructions` in the MCP
initialize response, so the "delegate substantial subtasks to ABS" behaviour
is turnkey from the server — no client-side CLAUDE.md required for the basics.
This pins that the instructions exist and name the headline delegation tools.
"""

from app.mcp.server import MCP_INSTRUCTIONS, mcp_server


def test_mcp_server_has_instructions():
    assert mcp_server.instructions
    assert mcp_server.instructions == MCP_INSTRUCTIONS


def test_instructions_name_headline_tools():
    text = MCP_INSTRUCTIONS.lower()
    # A representative tool from each delegation category should be mentioned.
    for tool in (
        "ask_gptoss",
        "ask_qwen32b",
        "ask_kimi",
        "qual_code",
        "race",
        "rag_query",
    ):
        assert tool in text, f"delegation instructions should mention {tool}"


def test_instructions_tell_client_to_delegate():
    assert "delegat" in MCP_INSTRUCTIONS.lower()
