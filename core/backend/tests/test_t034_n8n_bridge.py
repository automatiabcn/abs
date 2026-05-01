"""T-034 — n8n MCP bridge tests."""

from __future__ import annotations

import pytest

from app.workflow_v10.n8n_mcp_bridge import MCPToolRegistry, MCPToolSpec


def _spec(name: str = "rag.query") -> MCPToolSpec:
    return MCPToolSpec(
        name=name,
        description=f"{name} tool",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        requires_role="member",
    )


def test_register_and_list() -> None:
    reg = MCPToolRegistry()
    reg.register(_spec("rag.query"))
    reg.register(_spec("rag.ingest"))
    names = [t.name for t in reg.list_tools()]
    assert names == ["rag.ingest", "rag.query"]


def test_register_duplicate_raises() -> None:
    reg = MCPToolRegistry()
    reg.register(_spec())
    with pytest.raises(ValueError):
        reg.register(_spec())


def test_export_for_n8n_emits_node_specs() -> None:
    reg = MCPToolRegistry()
    reg.register(_spec("rag.query"))
    nodes = reg.export_for_n8n(gateway_url="https://abs.local")
    assert len(nodes) == 1
    n = nodes[0]
    assert n["name"] == "rag.query"
    assert n["type"] == "abs-mcp-connect"
    assert n["url"] == "https://abs.local/v1/mcp/invoke/rag.query"
    assert n["metadata"]["requires_role"] == "member"


def test_to_n8n_node_strips_trailing_slash() -> None:
    spec = _spec("rag.query")
    out = spec.to_n8n_node(gateway_url="https://abs.local/")
    assert out["url"] == "https://abs.local/v1/mcp/invoke/rag.query"
