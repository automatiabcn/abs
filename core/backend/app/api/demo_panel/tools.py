# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""033 Modul E — MCP tool browser API.

GET /v1/panel/tools  — every registered tool with name, description,
                       category, params shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/v1/panel", tags=["panel"])

# Heuristic prefix → category mapping. Keep small and stable.
_CATEGORY_RULES: list[tuple[str, str]] = [
    ("ask_compound", "agentic"),
    ("ask_cerebras_qwen", "upper"),
    ("ask_gemini_latest", "upper"),
    ("ask_gemini_pro_latest", "upper"),
    ("ask_", "provider"),
    ("gemini_", "provider"),
    ("race", "race"),
    ("qual_", "quality"),
    ("rag_", "rag"),
    ("judge_", "judge"),
    ("cohere_", "cohere"),
    ("fullstack", "fullstack"),
    ("vault_", "vault"),
    ("billing_", "billing"),
    ("email_", "email"),
    ("provider_", "provider"),
    ("smart_link", "integration"),
    ("compliance", "compliance"),
    ("security", "security"),
    ("admin_", "admin"),
    ("beta_", "beta"),
    ("news_", "research"),
    ("learnings_", "telemetry"),
    ("perf_", "telemetry"),
    ("wizard_", "telemetry"),
    ("workflow_", "workflow"),
    ("cache_", "system"),
    ("model_", "system"),
    ("system_", "system"),
    ("update_", "system"),
    ("setup_", "system"),
    ("status_", "system"),
    ("license_", "system"),
    ("demo_", "system"),
    ("breaker_", "system"),
    ("quota_", "system"),
    ("symbol_", "search"),
    ("score_", "quality"),
    ("write_", "quality"),
    ("code_", "quality"),
    ("apply_", "quality"),
    ("preview_", "quality"),
    ("freeze", "system"),
    ("investigate", "research"),
    ("humanize_", "quality"),
    ("auto_verify_", "quality"),
]


def _categorise(name: str) -> str:
    for prefix, cat in _CATEGORY_RULES:
        if name == prefix or name.startswith(prefix):
            return cat
    return "misc"


def _input_summary(schema: dict | None) -> dict:
    if not schema or not isinstance(schema, dict):
        return {"required": [], "properties": []}
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    return {
        "required": list(required),
        "properties": [
            {"name": k, "type": v.get("type") or "any"} for k, v in props.items()
        ],
    }


@router.get("/tools")
async def list_tools(category: str | None = None) -> dict:
    from app.mcp.server import mcp_server

    raw = await mcp_server.list_tools()
    items: list[dict[str, Any]] = []
    cat_counts: dict[str, int] = {}
    for tool in raw:
        cat = _categorise(tool.name)
        if category and cat != category:
            continue
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        items.append(
            {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "category": cat,
                "input_schema": _input_summary(getattr(tool, "inputSchema", None)),
            }
        )
    items.sort(key=lambda t: (t["category"], t["name"]))
    # Provide totals over the unfiltered set as well.
    full_total = len(raw)
    return {
        "total": full_total,
        "filtered_count": len(items),
        "category_counts": cat_counts,
        "tools": items,
    }
