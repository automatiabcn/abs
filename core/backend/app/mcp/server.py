# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""FastMCP sunucu instance'ı + tool kayıt noktası.

BUG-38 (2026-05-09) — FastMCP defaults to ``host="127.0.0.1"`` which
auto-enables DNS-rebinding protection with an allowlist of localhost
variants only. External callers (Hetzner sslip.io, customer custom
domains) hit `Invalid Host header` 421s before any tool ever runs.

The fix is a configurable allowlist: localhost stays in for in-container
healthchecks; we also allow ``*.sslip.io`` (IP-based pilots), the
operator-configured ``settings.domain``, and any extra hosts from the
``ABS_MCP_ALLOWED_HOSTS`` env (comma-separated). Wildcard ``*`` disables
the gate entirely for customers who terminate TLS upstream and trust
their network.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def _resolve_allowed_hosts() -> list[str]:
    """Compose the host allowlist from settings + env.

    Order:
      1. Localhost variants (always — in-container healthcheck).
      2. ``settings.domain`` (operator config) — both bare + ":*" pattern.
      3. Wildcard ``*.sslip.io`` for IP-based pilots.
      4. Extra hosts from ``ABS_MCP_ALLOWED_HOSTS`` (comma-separated).
      5. ``ABS_MCP_ALLOWED_HOSTS=*`` short-circuits to disabled gate.
    """

    hosts: list[str] = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]

    try:
        from app.config import settings

        domain = (settings.domain or "").strip()
    except Exception:  # pragma: no cover — boot before settings load
        domain = ""

    if domain and domain != "abs.local":
        hosts.append(domain)
        hosts.append(f"{domain}:*")

    # sslip.io family — wildcard subdomain pattern via "*.sslip.io"
    # is not a TransportSecurityMiddleware feature, so we add the most
    # common Hetzner pilot pattern explicitly. Customers on other
    # sslip patterns extend via ABS_MCP_ALLOWED_HOSTS.
    hosts.append("168.119.104.24.sslip.io")
    hosts.append("168.119.104.24.sslip.io:*")

    extra = os.environ.get("ABS_MCP_ALLOWED_HOSTS", "").strip()
    if extra == "*":
        # Sprint 2I UAT-020 — wildcard host allowlist on a production
        # deployment is a DNS-rebinding / cross-tenant Host-header
        # footgun. Refuse to boot in env=prod so operators cannot ship
        # the gate disabled by accident; dev / test keeps the opt-out.
        try:
            from app.config import settings as _s

            if (_s.env or "").lower() in ("prod", "production"):
                raise SystemExit(
                    "ABS refusing to boot: ABS_MCP_ALLOWED_HOSTS='*' "
                    "is forbidden in env=prod. Set ABS_MCP_ALLOWED_HOSTS "
                    "to an explicit host list (e.g. 'abs.your-domain.com')."
                )
        except SystemExit:
            raise
        except Exception:  # pragma: no cover — boot before settings load
            pass
        return ["*"]
    if extra:
        for h in (x.strip() for x in extra.split(",")):
            if h and h not in hosts:
                hosts.append(h)
                if ":*" not in h and not h.startswith("*"):
                    hosts.append(f"{h}:*")
    return hosts


def _build_security() -> TransportSecuritySettings | None:
    """Return the TransportSecuritySettings for FastMCP.

    Returns ``None`` (gate disabled) when the allowlist contains the
    wildcard ``*`` so customers who terminate TLS upstream can opt out.
    """
    hosts = _resolve_allowed_hosts()
    if "*" in hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    origins: list[str] = []
    for h in hosts:
        if h.endswith(":*") or h in {"127.0.0.1", "localhost", "[::1]"}:
            continue
        origins.append(f"https://{h}")
        origins.append(f"http://{h}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


# Server-side delegation guidance. The MCP `initialize` response carries this
# to every connecting client (Claude Code, Codex, …), so the "delegate to ABS"
# behaviour is turnkey from the server — no client-side CLAUDE.md required for
# the basics. English by default (the product ships globally); operators can
# still add a richer local CLAUDE.md. Keep it short — clients inline it.
MCP_INSTRUCTIONS = (
    "Automatia ABS exposes 100+ free / low-cost AI tools across many models, "
    "running on the operator's own provider keys (no extra Anthropic cost). "
    "PREFER delegating substantial subtasks to these tools instead of doing "
    "them yourself — it saves your tokens and often improves quality. Reach "
    "for them proactively:\n"
    "- Analysis / research / reasoning -> ask_gptoss (GPT-OSS 120B) or ask_gemini_pro\n"
    "- Code / a single function or endpoint -> ask_kimi or ask_qwen3_coder\n"
    "- Translation / non-English prose -> ask_qwen32b\n"
    "- Fast classification / short factual answers -> ask_groq_fast or ask_scout\n"
    "- Quality over speed (generate->verify->fix chain) -> qual_code, qual_analysis, qual_translate\n"
    "- Parallel race, fastest of several models -> race, race_code\n"
    "- Code review / unit tests / docs -> code_review, write_tests, write_docs\n"
    "- Project knowledge base -> rag_query.  System health -> system_status."
)

# streamable_http_path="/" → inner route root'ta; ana app /mcp altına mount eder.
# host="0.0.0.0" so the auto-localhost-only allowlist is NOT applied
# (we install our own via transport_security).
mcp_server = FastMCP(
    "Automatia ABS",
    instructions=MCP_INSTRUCTIONS,
    streamable_http_path="/",
    host="0.0.0.0",
    transport_security=_build_security(),
)


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
