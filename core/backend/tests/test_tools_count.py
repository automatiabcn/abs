"""Feature Parity guard — registered MCP tool count (after 010 89+)."""

from __future__ import annotations

import asyncio


def test_registered_tool_count_at_least_122():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    # 120 default: preview_patch + apply_patch are now gated off the MCP surface
    # (ABS_MCP_EXPOSE_PATCH_TOOLS, default off) because they read/write arbitrary
    # files — see test_patch_tools_gated_off_by_default below.
    assert len(tools) >= 120, f"Tool sayısı düştü: {len(tools)}"


def test_billing_status_tool_registered_017():
    """verify billing_status tool alone in registry."""
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "billing_status" in names, (
        f"billing_status registry'de yok: {sorted(names)[:10]}..."
    )


def test_email_queue_status_tool_registered_019():
    """email_queue_status tool'u registry'de."""
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "email_queue_status" in names


def test_core_tool_names_registered():
    """Task 008 + 009 + 010 critical tools must be registered."""
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}

    must_have = {
        # 005
        "ask_groq_fast",
        "ask_cerebras",
        "ask_gemini",
        "system_status",
        # 006
        "qual_code",
        "qual_tr",
        "race_code",
        "ask_sonnet",
        # 008 Batch A
        "judge_patch",
        "write_tests",
        "write_docs",
        "code_review",
        "ask_disagree",
        "score_patch_quality",
        # 008 Batch B
        "ask_smart",
        "ask_rerank",
        "ask_aya",
        "ask_granite",
        "ask_deepseek",
        "ask_or_qwen_coder",
        "ask_reasoner",
        # 008 Batch C
        "gemini_search",
        "gemini_url",
        "gemini_structured",
        "gemini_image",
        # 008 Batch D
        "ask_cohere_command_r",
        "ask_cohere_embed",
        # 008 Batch E
        "cache_stats",
        "quota_status",
        "model_health",
        "code_fingerprint",
        # preview_patch / apply_patch intentionally NOT here — gated off the
        # default MCP surface (arbitrary file read/write). See test below.
        # 008 Batch F
        "fullstack",
        "fullstack_detect",
        "fullstack_scan",
        "fullstack_plan",
        # 008 Batch G
        "freeze",
        "investigate",
        # 009 — workflow durability
        "workflow_status",
        "workflow_resume",
        # 009 — judge log + stats
        "judge_stats",
        "judge_recent",
        "judge_outcome",
        # 009 — cohere alert pipeline
        "cohere_alert_status",
        "cohere_alerts_recent",
        "cohere_alert_ack",
        # 009 — RAG
        "rag_index",
        "rag_query",
        "rag_status",
        "rag_clear",
        # 010 — MLX provider
        "ask_mlx",
        "ask_mlx_fast",
        # 010 — Judge persona live training
        "judge_persona_status",
        "judge_persona_train",
        "judge_persona_reset",
        # 011 — License/demo tools
        "license_status",
        "demo_status",
        # 012 — Setup wizard
        "setup_status",
        # 013 — Vault status
        "vault_status",
        # 014 — Update + health + breaker
        "update_check",
        "health_status",
        "breaker_status",
        # 015 — Billing + learnings
        "daily_cost",
        "learnings_recent",
        "learnings_log",
        # 016 — Innovation: symbol + RAG hybrid + ML persona predict
        "symbol_search",
        "rag_hybrid",
        "judge_persona_predict",
        # 017 — Stripe billing dashboard
        "billing_status",
        # 019 — Email queue dashboard
        "email_queue_status",
        # 021 — Performance benchmark summary
        "perf_summary",
        # 022 — Wizard funnel
        "wizard_funnel",
        # 023 — System validate
        "system_validate",
        # 025 — Status check
        "status_check",
        # 026 — Smart link production
        "smart_link_status",
        "provider_validate",
        # 027 — Vault audit
        "vault_audit_status",
        # 028 — Security audit
        "security_audit",
        # 029 — Compliance status
        "compliance_status",
        # 030 — Compound (agentic) + upper-tier + auto-upgrade + news
        "ask_compound",
        "ask_compound_mini",
        "ask_cerebras_qwen",
        "ask_gemini_latest",
        "ask_gemini_pro_latest",
        "news_digest",
        # 031 — Beta metrics
        "beta_metrics",
        # 032 — Admin overview
        "admin_overview",
        # 033 — Demo readiness status
        "demo_readiness_status",
    }
    missing = must_have - names
    assert not missing, f"Eksik tool'lar: {sorted(missing)}"


def test_patch_tools_gated_off_by_default():
    """SECURITY: preview_patch + apply_patch read/write arbitrary files on the
    server (no path allowlist). They must NOT be exposed on the network /mcp
    surface by default — any delegation token-holder could otherwise read
    secrets or patch a loaded module (RCE). Opt-in via ABS_MCP_EXPOSE_PATCH_TOOLS.
    """
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    assert "apply_patch" not in names, "apply_patch must be gated off /mcp by default"
    assert "preview_patch" not in names, (
        "preview_patch must be gated off /mcp by default"
    )
