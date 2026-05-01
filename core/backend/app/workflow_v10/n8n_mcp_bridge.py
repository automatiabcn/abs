"""T-034 — n8n ↔ ABS MCP catalog bridge.

Exposes the registered ABS MCP tool names as n8n-callable specs and proxies
invocations through the existing Cerbos + JWT-aware gateway. This module
handles the metadata side; the actual HTTP forwarder lives in n8n's `MCP
Connect` community node, which `register_tool_spec` returns config for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "MCPToolSpec",
    "MCPToolRegistry",
]


@dataclass(slots=True)
class MCPToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_role: str = "member"
    metadata: dict[str, str] = field(default_factory=dict)

    def to_n8n_node(self, *, gateway_url: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "abs-mcp-connect",
            "description": self.description,
            "credentials": ["abs_jwt"],
            "url": f"{gateway_url.rstrip('/')}/v1/mcp/invoke/{self.name}",
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "metadata": {"requires_role": self.requires_role, **self.metadata},
        }


class MCPToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, MCPToolSpec] = {}

    def register(self, spec: MCPToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} already registered")
        self._tools[spec.name] = spec
        logger.info("mcp_tool_register name=%s role=%s", spec.name, spec.requires_role)

    def list_tools(self) -> list[MCPToolSpec]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def export_for_n8n(self, *, gateway_url: str) -> list[dict[str, Any]]:
        return [t.to_n8n_node(gateway_url=gateway_url) for t in self.list_tools()]
