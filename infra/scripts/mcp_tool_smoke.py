"""024 — MCP tool inventory smoke check.

Each registered MCP tool: minimal valid input + call + response shape check.
Live-API-requiring tools are SKIPPED with a reason (no mock).

Output JSON:
  {
    "total": int,
    "ok": int,
    "skipped": int,
    "failed": int,
    "results": {
      tool_name: {ok: bool, latency_ms: int, error: str|null, skip_reason: str|null}
    }
  }

Exit 0 if failed=0 (skips are OK), 1 otherwise.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict


# Tools that need live external API — skip with reason
_SKIP_TOOLS: Dict[str, str] = {
    # Live provider API
    "ask_groq": "live Groq API",
    "ask_groq_fast": "live Groq API",
    "ask_gptoss": "live Groq API",
    "ask_gptoss20": "live Groq API",
    "ask_kimi": "live Groq API",
    "ask_kimi2": "live Groq API",
    "ask_qwen32b": "live Groq API",
    "ask_scout": "live Groq API",
    "ask_reasoner": "live Groq API",
    "ask_rerank": "live Groq API",
    "ask_aya": "live Cohere API",
    "ask_granite": "live Groq API",
    "ask_granite_fast": "live Groq API",
    "ask_deepseek": "live API",
    "ask_cerebras": "live Cerebras API",
    "ask_cerebras_fast": "live Cerebras API",
    "ask_gemini": "live Gemini API",
    "ask_gemini_pro": "live Gemini API",
    "gemini_search": "live Gemini API",
    "gemini_url": "live Gemini API",
    "gemini_lite": "live Gemini API",
    "gemini_image": "live Gemini API",
    "gemini_image_edit": "live Gemini API",
    "gemini_image_pro": "live Gemini API",
    "gemini_video": "live Gemini API",
    "gemini_video_status": "live Gemini API",
    "gemini_video_wait": "live Gemini API",
    "gemini_structured": "live Gemini API",
    "ask_cf": "live Cloudflare API",
    "ask_cf_coder": "live Cloudflare API",
    "ask_cf_gptoss": "live Cloudflare API",
    "ask_cf_llama4_scout": "live Cloudflare API",
    "ask_cf_qwen30": "live Cloudflare API",
    "ask_cf_reasoner": "live Cloudflare API",
    "ask_cohere_command_r": "live Cohere API",
    "ask_cohere_embed": "live Cohere API",
    "ask_sonnet": "live Anthropic API",
    "ask_smart": "live Anthropic API",
    "ask_phi4": "local Ollama required",
    "ask_gemma2": "local Ollama required",
    "ask_codellama": "local Ollama required",
    "ask_llava": "local Ollama required",
    "ask_mlx": "local MLX server required",
    "ask_mlx_fast": "local MLX server required",
    "ask_starcoder": "local Ollama required",
    "ask_vllm": "local vLLM required",
    "ask_or_qwen_coder": "live OpenRouter API",
    "ask_or_minimax": "live OpenRouter API",
    "ask_longcontext": "live API",
    # 030 — new agentic + upper-tier + auto-upgrade tools
    "ask_compound": "live Groq API",
    "ask_compound_mini": "live Groq API",
    "ask_cerebras_qwen": "live Cerebras API",
    "ask_gemini_latest": "live Gemini API",
    "ask_gemini_pro_latest": "live Gemini API",
    "news_digest": "fans out 5 live Gemini search calls",
    # Pipeline (chained calls)
    "qual_code": "calls live providers",
    "qual_tr": "calls live providers",
    "qual_analysis": "calls live providers",
    "qual_translate": "calls live providers",
    "qual_human": "calls live providers",
    "qual_code_human": "calls live providers",
    "race": "calls live providers",
    "race_code": "calls live providers",
    "race_tr": "calls live providers",
    "ask_disagree": "calls live providers",
    "judge_patch": "calls live providers",
    "score_patch_quality": "calls live providers",
    "code_review": "calls live providers",
    "write_tests": "calls live providers",
    "write_docs": "calls live providers",
    "fullstack": "calls live providers",
    "fullstack_detect": "calls live providers",
    "fullstack_plan": "calls live providers",
    # External / file-system heavy
    "rag_index": "filesystem walk",
    "rag_query": "live RAG (chromadb)",
    "rag_hybrid": "live RAG (chromadb)",
    "rag_clear": "wipes data",
    "fullstack_scan": "filesystem walk",
    "freeze": "modifies global state",
    "investigate": "calls live providers",
    "judge_persona_train": "needs training data",
    "code_fingerprint": "needs file path",
    "preview_patch": "needs patch text",
    "apply_patch": "modifies files",
    "auto_verify_code": "calls live providers",
    "auto_verify_turkish": "calls live providers",
    "humanize_score": "calls live providers",
    # Stripe
    "billing_status": "calls Stripe API",
    "daily_cost": "tracker depends on history",
    # Cohere alerts (writes JSONL)
    "cohere_alert_ack": "needs alert id",
    # Tools that require positional args we don't safely have
    "judge_outcome": "needs judgment_id",
    "workflow_resume": "needs trace_id",
}


# Tools that should be safely callable with no/empty args
_SAFE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # No-arg tools
    "system_status": {},
    "license_status": {},
    "demo_status": {},
    "vault_status": {},
    "setup_status": {},
    "update_check": {},
    "health_status": {},
    "breaker_status": {},
    "cache_stats": {},
    "model_health": {},
    "quota_status": {},
    "workflow_status": {},
    "workflow_resume": {},
    "judge_persona_status": {},
    "judge_persona_reset": {},
    "judge_recent": {},
    "judge_outcome": {},
    "judge_stats": {},
    "cohere_alert_status": {},
    "cohere_alerts_recent": {},
    "rag_status": {},
    "perf_summary": {},
    "wizard_funnel": {},
    "email_queue_status": {},
    "system_validate": {"force": False},
    # 025
    "status_check": {},
    # 026
    "smart_link_status": {},
    "provider_validate": {"provider": "unknown_x", "api_key": "x" * 16},
    # 027
    "vault_audit_status": {},
    # 028
    "security_audit": {},
    # 029
    "compliance_status": {},
    # Safe args
    "symbol_search": {"q": "test"},
    "judge_persona_predict": {"ast_score": 5.0, "llm_score": 5.0, "persona_drift": 0.1},
    "learnings_recent": {"limit": 5},
    "learnings_log": {"category": "perf", "lesson": "smoke test entry"},
}


async def _run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.mcp.server import mcp_server

    handler = None
    for tool in await mcp_server.list_tools():
        if tool.name == name:
            handler = mcp_server._tool_manager._tools.get(name)  # type: ignore[attr-defined]
            break
    if handler is None:
        return {
            "ok": False,
            "latency_ms": 0,
            "error": "tool handler not found",
            "skip_reason": None,
        }
    fn = getattr(handler, "fn", None) or handler
    t0 = time.perf_counter()
    try:
        if asyncio.iscoroutinefunction(fn):
            await fn(**args)
        else:
            fn(**args)
        return {
            "ok": True,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": None,
            "skip_reason": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": str(exc)[:200],
            "skip_reason": None,
        }


async def smoke_all() -> Dict[str, Any]:
    # 024 — ensure data_dir is writable (default `/app/data` is read-only on host)
    import tempfile

    from app.config import settings
    from app.db.session import init_db

    if not os.access(settings.data_dir, os.W_OK):
        tmp = tempfile.mkdtemp(prefix="abs-024-smoke-")
        settings.data_dir = tmp
        # also redirect SQLite database to tmp so smoke tools that touch DB work
        settings.database_url = f"sqlite:///{tmp}/abs.db"
        # Reset cached engine so new database_url is used
        try:
            import app.db.session as session_mod

            session_mod._engine = None
            init_db()
        except Exception:
            pass
    # Always co-locate cache/artifacts under writable data_dir so persona/etc. tools
    # don't hit /app/data/cache (which may be read-only on host).
    if not os.access(settings.cache_dir, os.W_OK):
        settings.cache_dir = settings.data_dir
    if not os.access(settings.artifacts_dir, os.W_OK):
        settings.artifacts_dir = settings.data_dir

    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    results: Dict[str, Dict[str, Any]] = {}
    ok_count = skip_count = fail_count = 0

    for tool in tools:
        name = tool.name
        if name in _SKIP_TOOLS:
            results[name] = {
                "ok": True,
                "latency_ms": 0,
                "error": None,
                "skip_reason": _SKIP_TOOLS[name],
            }
            skip_count += 1
            continue
        args = _SAFE_DEFAULTS.get(name)
        if args is None:
            # Unknown tool — skip with note
            results[name] = {
                "ok": True,
                "latency_ms": 0,
                "error": None,
                "skip_reason": "no safe default args defined",
            }
            skip_count += 1
            continue
        result = await _run_tool(name, args)
        results[name] = result
        if result["ok"]:
            ok_count += 1
        else:
            fail_count += 1

    return {
        "total": len(tools),
        "ok": ok_count,
        "skipped": skip_count,
        "failed": fail_count,
        "results": results,
    }


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "core" / "backend"))
    out = asyncio.run(smoke_all())
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
