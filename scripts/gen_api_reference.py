# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""020 — MCP tool listesi otomatik üret → docs/api-reference.md.

Her release'de bu script çalışır:
  python scripts/gen_api_reference.py

Kategorilere göre grup, isim alfabetik, açıklama tool docstring'inden.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Dict, List


# Tool kategorileri — prefix bazlı
_CATEGORIES = [
    ("Sistem & Sağlık", ["system_status", "health_status", "model_health", "breaker_status",
                         "setup_status", "license_status", "demo_status", "vault_status",
                         "update_check", "billing_status", "email_queue_status", "cache_stats",
                         "code_fingerprint", "freeze", "investigate", "preview_patch",
                         "apply_patch", "humanize_score", "auto_verify_code",
                         "auto_verify_turkish", "daily_cost", "learnings_recent",
                         "learnings_log", "quota_status", "workflow_status",
                         "workflow_resume", "judge_persona_status", "judge_persona_train",
                         "judge_persona_reset", "judge_persona_predict", "judge_recent",
                         "judge_outcome", "judge_stats", "judge_patch", "score_patch_quality",
                         "code_review", "write_tests", "write_docs"]),
    ("Provider — Anthropic", ["ask_sonnet", "ask_smart"]),
    ("Provider — Groq", ["ask_groq", "ask_groq_fast", "ask_gptoss", "ask_gptoss20",
                          "ask_kimi", "ask_kimi2", "ask_qwen32b", "ask_scout",
                          "ask_reasoner", "ask_rerank", "ask_aya", "ask_granite",
                          "ask_granite_fast", "ask_deepseek"]),
    ("Provider — Cerebras", ["ask_cerebras", "ask_cerebras_fast"]),
    ("Provider — Gemini", ["ask_gemini", "ask_gemini_pro", "gemini_search", "gemini_url",
                            "gemini_lite", "gemini_image", "gemini_image_edit",
                            "gemini_image_pro", "gemini_video", "gemini_video_status",
                            "gemini_video_wait", "gemini_structured"]),
    ("Provider — Cloudflare", ["ask_cf", "ask_cf_coder", "ask_cf_gptoss",
                                "ask_cf_llama4_scout", "ask_cf_qwen30",
                                "ask_cf_reasoner"]),
    ("Provider — Cohere", ["ask_cohere_command_r", "ask_cohere_embed",
                            "cohere_alert_status", "cohere_alerts_recent",
                            "cohere_alert_ack"]),
    ("Provider — Lokal", ["ask_phi4", "ask_gemma2", "ask_codellama", "ask_llava",
                           "ask_mlx", "ask_mlx_fast", "ask_starcoder", "ask_vllm",
                           "ask_or_qwen_coder", "ask_or_minimax", "ask_longcontext"]),
    ("Pipeline — Kalite", ["qual_code", "qual_tr", "qual_analysis", "qual_translate",
                            "qual_human", "qual_code_human", "race", "race_code",
                            "race_tr", "ask_disagree"]),
    ("RAG", ["rag_index", "rag_query", "rag_status", "rag_clear", "rag_hybrid",
             "symbol_search"]),
    ("Fullstack", ["fullstack", "fullstack_detect", "fullstack_scan", "fullstack_plan"]),
]


def _category_for(name: str) -> str:
    for cat, names in _CATEGORIES:
        if name in names:
            return cat
    return "Diğer"


async def _collect_tools() -> List[dict]:
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    out = []
    for t in tools:
        out.append(
            {
                "name": t.name,
                "description": (t.description or "").strip().split("\n")[0],
                "input_schema": getattr(t, "inputSchema", None) or {},
            }
        )
    return sorted(out, key=lambda x: x["name"].lower())


def _render_md(tools: List[dict]) -> str:
    by_cat: Dict[str, List[dict]] = {}
    for t in tools:
        cat = _category_for(t["name"])
        by_cat.setdefault(cat, []).append(t)

    lines: List[str] = []
    lines.append("# API Reference — MCP Tools\n")
    lines.append(
        "Bu sayfa otomatik üretilir (`python scripts/gen_api_reference.py`). Manuel düzenleme yapma.\n"
    )
    lines.append(
        f"Toplam **{len(tools)} tool** — kategorilere göre alfabetik sıralı.\n"
    )
    lines.append(
        "Her MCP tool, Claude Code'da `claude mcp add abs <url>` sonrası `mcp__abs__<tool>` "
        "olarak veya orchestrator alias'larla (`ask \"...\" gptoss` vb.) çağrılabilir.\n\n"
    )

    cat_order = [c for c, _ in _CATEGORIES] + ["Diğer"]
    for cat in cat_order:
        if cat not in by_cat:
            continue
        lines.append(f"## {cat}\n\n")
        lines.append(f"_{len(by_cat[cat])} tool_\n\n")
        for t in by_cat[cat]:
            desc = t["description"] or "(açıklama yok)"
            lines.append(f"### `{t['name']}`\n")
            lines.append(f"{desc}\n\n")
            schema = t["input_schema"] or {}
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            if props:
                lines.append("**Parametreler:**\n\n")
                lines.append("| İsim | Tip | Zorunlu | Açıklama |\n")
                lines.append("|---|---|:-:|---|\n")
                for pname, pdef in props.items():
                    ptype = pdef.get("type", "?")
                    pdesc = (pdef.get("description") or "").replace("\n", " ")[:120]
                    req = "✓" if pname in required else ""
                    lines.append(f"| `{pname}` | `{ptype}` | {req} | {pdesc} |\n")
                lines.append("\n")
        lines.append("---\n\n")

    return "".join(lines)


def main() -> int:
    tools = asyncio.run(_collect_tools())
    md = _render_md(tools)
    out_path = Path(__file__).resolve().parent.parent / "docs" / "api-reference.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path} — {len(tools)} tools")
    return 0


if __name__ == "__main__":
    # Çalıştırmadan önce app modulünü import edebilmek için PYTHONPATH ayarla
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "core" / "backend"))
    sys.exit(main())
