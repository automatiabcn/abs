# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""FastMCP sunucu instance'ı + tool kayıt noktası."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# streamable_http_path="/" → inner route root'ta; ana app /mcp altına mount eder.
mcp_server = FastMCP("Automatia ABS", streamable_http_path="/")


def http_app():
    return mcp_server.streamable_http_app()


def register_all_tools() -> int:
    """Tüm tool modüllerini içe aktararak FastMCP'ye register et."""
    from app.mcp.tools import anthropic_tools  # noqa: F401
    from app.mcp.tools import basic_providers  # noqa: F401
    from app.mcp.tools import billing_tools  # noqa: F401  (015)
    from app.mcp.tools import email_tools  # noqa: F401  (019)
    from app.mcp.tools import perf_tools  # noqa: F401  (021)
    from app.mcp.tools import wizard_tools  # noqa: F401  (022)
    from app.mcp.tools import validate_tools  # noqa: F401  (023)
    from app.mcp.tools import status_tools  # noqa: F401  (025)
    from app.mcp.tools import smart_link_tools  # noqa: F401  (026)
    from app.mcp.tools import vault_audit_tools  # noqa: F401  (027)
    from app.mcp.tools import security_tools  # noqa: F401  (028)
    from app.mcp.tools import compliance_tools  # noqa: F401  (029)
    from app.mcp.tools import compound_tools  # noqa: F401  (030)
    from app.mcp.tools import upper_tier_tools  # noqa: F401  (030)
    from app.mcp.tools import news_digest as news_digest_mod  # noqa: F401  (030)
    from app.mcp.tools import beta_tools  # noqa: F401  (031)
    from app.mcp.tools import admin_tools  # noqa: F401  (032)
    from app.mcp.tools import demo_tools  # noqa: F401  (033)
    from app.mcp.tools import cohere_alert  # noqa: F401  (009)
    from app.mcp.tools import cohere_tools  # noqa: F401
    from app.mcp.tools import fullstack as fullstack_mod  # noqa: F401
    from app.mcp.tools import gemini_extras as gemini_mod  # noqa: F401
    from app.mcp.tools import hook_companions  # noqa: F401
    from app.mcp.tools import innovation_tools  # noqa: F401  (016)
    from app.mcp.tools import judge_extras  # noqa: F401  (009)
    from app.mcp.tools import judge_persona  # noqa: F401  (010)
    from app.mcp.tools import license_tools  # noqa: F401  (011)
    from app.mcp.tools import pipelines  # noqa: F401
    from app.mcp.tools import provider_extras  # noqa: F401
    from app.mcp.tools import quality  # noqa: F401
    from app.mcp.tools import rag as rag_tools  # noqa: F401  (009)
    from app.mcp.tools import setup_tools  # noqa: F401  (012)
    from app.mcp.tools import system as _system  # noqa: F401
    from app.mcp.tools import system_extras  # noqa: F401
    from app.mcp.tools import update_tools  # noqa: F401  (014)
    from app.mcp.tools import vault_tools  # noqa: F401  (013)
    from app.mcp.tools import workflow as wf_tools  # noqa: F401  (009)

    return (
        len(basic_providers.REGISTERED_TOOLS)
        + len(pipelines.REGISTERED_TOOLS)
        + len(anthropic_tools.REGISTERED_TOOLS)
        + len(quality.REGISTERED_TOOLS)
        + len(provider_extras.REGISTERED_TOOLS)
        + len(gemini_mod.REGISTERED_TOOLS)
        + len(cohere_tools.REGISTERED_TOOLS)
        + len(system_extras.REGISTERED_TOOLS)
        + len(fullstack_mod.REGISTERED_TOOLS)
        + len(hook_companions.REGISTERED_TOOLS)
        + len(wf_tools.REGISTERED_TOOLS)
        + len(judge_extras.REGISTERED_TOOLS)
        + len(cohere_alert.REGISTERED_TOOLS)
        + len(rag_tools.REGISTERED_TOOLS)
        + len(judge_persona.REGISTERED_TOOLS)  # 010 — 3 tool
        + len(license_tools.REGISTERED_TOOLS)  # 011 — 2 tool
        + len(setup_tools.REGISTERED_TOOLS)  # 012 — 1 tool
        + len(vault_tools.REGISTERED_TOOLS)  # 013 — 1 tool
        + len(update_tools.REGISTERED_TOOLS)  # 014 — 3 tool
        + len(billing_tools.REGISTERED_TOOLS)  # 015 — 3 tool + 017 — billing_status
        + len(email_tools.REGISTERED_TOOLS)  # 019 — email_queue_status
        + len(perf_tools.REGISTERED_TOOLS)  # 021 — perf_summary
        + len(wizard_tools.REGISTERED_TOOLS)  # 022 — wizard_funnel
        + len(validate_tools.REGISTERED_TOOLS)  # 023 — system_validate
        + len(status_tools.REGISTERED_TOOLS)  # 025 — status_check
        + len(smart_link_tools.REGISTERED_TOOLS)  # 026 — smart_link_status, provider_validate
        + len(vault_audit_tools.REGISTERED_TOOLS)  # 027 — vault_audit_status
        + len(security_tools.REGISTERED_TOOLS)  # 028 — security_audit
        + len(compliance_tools.REGISTERED_TOOLS)  # 029 — compliance_status
        + len(compound_tools.REGISTERED_TOOLS)  # 030 — ask_compound, ask_compound_mini
        + len(upper_tier_tools.REGISTERED_TOOLS)  # 030 — cerebras_qwen + 2 gemini latest aliases
        + len(news_digest_mod.REGISTERED_TOOLS)  # 030 — news_digest
        + len(beta_tools.REGISTERED_TOOLS)  # 031 — beta_metrics
        + len(admin_tools.REGISTERED_TOOLS)  # 032 — admin_overview
        + len(demo_tools.REGISTERED_TOOLS)  # 033 — demo_readiness_status
        + len(innovation_tools.REGISTERED_TOOLS)  # 016 — 3 tool
        + 1  # system_status
    )


_REGISTERED_COUNT = register_all_tools()
