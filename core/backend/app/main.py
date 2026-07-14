# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth as auth_router
from app.api.v1.projects import router as v1_projects_router
from app.api.v1.rag import router as v1_rag_router
from app.api.v1.agents import router as v1_agents_router  # Agentic core
from app.api.v1.approvals import router as v1_approvals_router  # Approval Center
from app.api.v1.inbound import router as v1_inbound_router  # MVP: Inbound + Knowledge
from app.api.v1.dashboard import router as v1_dashboard_router  # Growth Dashboard
from app.api.v1.leads import router as v1_leads_router  # Lead Intelligence
from app.api.v1.context_graph import (
    router as v1_context_graph_router,
)  # Context Graph + ER
from app.api.v1.connectors import (
    router as v1_connectors_router,
)  # Connector Marketplace
from app.api.v1.agentic_workflows import (
    router as v1_agentic_wf_router,
)  # Workflow Designer
from app.api.v1.consent import router as v1_consent_router  # Consent Ledger
from app.auth.oauth.routes import router as oauth_router
from app.api import beta_admin as beta_admin_router
from app.api import beta_portal as beta_portal_router
from app.api import billing_portal as billing_portal_router
from app.api.admin import analytics_licenses as admin_analytics_router
from app.api.admin import licenses as admin_licenses_router
from app.api.admin import audit_recent as admin_audit_router
from app.api.admin import auth as admin_auth_router
from app.api.admin import churn as admin_churn_router
from app.api.admin import dashboard as admin_dashboard_router
from app.api.admin import errors_recent as admin_errors_router
from app.api.admin import usage as admin_usage_router  # /v1/admin/usage
from app.api.admin import users as admin_users_router  # /v1/admin/users
from app.api.admin import widget_pricing as admin_widget_pricing_router
from app.api.admin import providers_status as admin_providers_status_router  # Polish R7
from app.api.admin import tenant as admin_tenant_router
from app.api.admin import (
    providers_save as admin_providers_save_router,
)
from app.api.admin import (
    provider_keys as admin_provider_keys_router,
)  # MT Phase 1 — per-owner keys
from app.api.admin import (
    projects as admin_projects_router,
)  # MT Phase 1 — project CRUD + membership
from app.api.admin import (
    settings_store as admin_settings_store_router,
)  # /admin/settings persistence
from app.api import demo_mode as demo_mode_router
from app.api.demo_panel import cascade as panel_cascade_router
from app.api.demo_panel import pipeline as panel_pipeline_router
from app.api.demo_panel import tools as panel_tools_router
from app.api import checkout as checkout_router
from app.api import demo_admin as demo_admin_router
from app.api import disagreement as disagreement_router
from app.api import vault_admin as vault_admin_router
from app.api import email_unsubscribe as email_unsubscribe_router
from app.api import health_full as health_full_router
from app.api import hooks as hooks_router
from app.api import license as license_router
from app.api import me_account as me_account_router
from app.api import me_audit as me_audit_router
from app.api import me_consent as me_consent_router
from app.api import me_data_export as me_data_export_router
from app.api import panel as panel_router
from app.api import cascade as cascade_router  # /v1/cascade/*
from app.api import agent_caps as agent_caps_router  # /v1/agent/capabilities
from app.api import chat as chat_router  # /v1/chat/*
from app.api import mcp_tokens as mcp_tokens_router  # /v1/mcp/tokens
from app.api import claude_code_hooks as cc_hooks_router  # /v1/hooks/*
from app.api import marketplace as marketplace_router  # /v1/marketplace/*
from app.api import meetings as meetings_router  # S20.4 — /v1/meetings
from app.api import workflows as workflows_router  # P1 S19 — /v1/workflows
from app.api import graph as graph_router  # /v1/graph
from app.api import graph_rag as graph_rag_router  # GraphRAG — /v1/graph-rag
from app.api import quota as quota_router
from app.api.system import (
    quota as system_quota_router,
)  # /v1/system/quota_status
from app.api.system import feature_usage as system_feature_usage_router  # S20.3
from app.api import transcribe as transcribe_router  # S20.2
from app.api import tts as tts_router  # S20.1
from app.api import secrets as secrets_router
from app.api import setup as setup_router
from app.api import smart_link as smart_link_router
from app.api import status_page as status_page_router
from app.api.integrations import slack as slack_router
from app.api.integrations import github_app as github_app_router
from app.api import stream as stream_router
from app.api import update as update_router
from app.api import symbol_graph as symbol_graph_router
from app.api.webhooks import stripe as stripe_webhook_router
from app.db.session import get_engine, init_db
from app.mcp.server import http_app as mcp_http_app
from app.mcp.server import mcp_server
from app.middleware.demo_mode import DemoModeMiddleware
from app.middleware.first_run import FirstRunMiddleware
from app.middleware.i18n import I18nMiddleware
from app.middleware.rate_limit import install_rate_limit
from app.middleware.request_id import RequestIDMiddleware

SETUP_STATIC_DIR = Path(__file__).resolve().parent / "static" / "setup"
# Brief 4 R4 — ADMIN_STATIC_DIR removed; /admin/* is Next.js territory
# served by the `landing` container behind the Caddy route split.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import logging

    init_db()
    _lf_logger = logging.getLogger("app.lifespan")

    # Restore persisted circuit-breaker state on boot. The breaker writes
    # every open/half-open transition to disk (persist.py) so a provider that
    # tripped before a deploy/restart stays isolated instead of being hammered
    # again on the first post-restart request. The restore method existed but
    # was never wired into startup, so the documented "open state survives
    # restart" guarantee silently never fired. Best-effort: never block boot.
    try:
        from app.cascade.breaker import default_breaker

        _restored = default_breaker.restore_state()
        if _restored:
            _lf_logger.info("circuit-breaker state restored: %s provider(s)", _restored)
    except Exception as exc:
        _lf_logger.warning("circuit-breaker restore skipped: %s", exc)

    # Agentic Growth — seed the demo dataset so every Growth screen renders the
    # populated mockup experience. Demo-mode only (never touches a real tenant's
    # data) and idempotent. Best-effort: a seed failure must not block boot.
    from app.config import settings as _seed_settings

    if getattr(_seed_settings, "demo_mode", False):
        try:
            from app.growth_seed import seed_growth_demo

            _seed = seed_growth_demo("default")
            if not _seed.get("skipped"):
                _lf_logger.info("growth demo seeded: %s", _seed)
        except Exception as exc:
            _lf_logger.warning("growth demo seed skipped: %s", exc)

    # Install secret-bearing query-param sanitizer on
    # httpx / uvicorn-access loggers so a regression elsewhere can't re-leak
    # credentials via URL logs (defence-in-depth alongside header auth).
    try:
        from app.observability.url_sanitizer import install_url_log_sanitizer

        install_url_log_sanitizer()
    except Exception as exc:
        _lf_logger.warning("url sanitizer install skipped: %s", exc)

    # Vault: plaintext .env migration + boot decrypt → settings'e bind
    try:
        from app.vault.migration import migrate_plaintext_env_to_vault

        migrated = migrate_plaintext_env_to_vault()
        if migrated:
            _lf_logger.info("vault migration: %d secrets moved from .env", migrated)
    except Exception as exc:
        _lf_logger.warning("vault migration skipped: %s", exc)
    try:
        from app.vault.cache import boot_load

        loaded = boot_load()
        if loaded:
            _lf_logger.info("vault boot: %d secrets loaded into settings", loaded)
    except Exception as exc:
        _lf_logger.warning("vault boot_load skipped: %s", exc)

    # Detect ABS_ANTHROPIC_ENABLED opt-in flips and emit
    # a SOC2 audit row (PROMISE.md "every opt-in flip ... audit log").
    try:
        from app.config import settings as _optin_settings
        from app.observability.optin_state import detect_and_emit_flip

        detect_and_emit_flip(current_enabled=bool(_optin_settings.anthropic_enabled))
    except Exception as exc:
        _lf_logger.warning("optin flip detection skipped: %s", exc)

    # No license key on this install → start the demo license (idempotent).
    from app.config import settings as _settings

    if not _settings.license_key:
        try:
            from app.licensing.demo import start_demo

            start_demo()
        except Exception:
            pass

    # IP hardening + Patch A (2026-05-08) — verifier tamper check.
    # Production: reads /etc/abs.verifier.hash (written by Dockerfile
    # builder stage from the shipped .so) and panics on mismatch.
    # No-op when neither /etc/abs.verifier.hash nor ABS_VERIFIER_HASH
    # is set (dev) or when ABS_TAMPER_CHECK_DISABLED=1 (test).
    # Exception propagates — boot must fail on tamper detection.
    try:
        from app.licensing.tamper_check import assert_self_integrity

        assert_self_integrity()
    except Exception as exc:
        _lf_logger.critical("tamper_check_failed: %s", exc)
        raise

    # IP hardening — online activation phone-home.
    # Fail-open within 7 days (server outage MUST NOT brick paying
    # customers). Skipped under ABS_TEST_MODE=1 and when activation is
    # disabled via ABS_PHONE_HOME_DISABLED=1 (dev convenience only —
    # production builds ignore this knob via Cython compile).
    import os as _ph_os

    _heartbeat_task = None  # for cleanup in finally
    if (
        _settings.license_key
        and _ph_os.environ.get("ABS_TEST_MODE") != "1"
        and _ph_os.environ.get("ABS_PHONE_HOME_DISABLED") != "1"
    ):
        try:
            from app.licensing.fingerprint import collect_machine_fingerprint
            from app.licensing.phone_home import activate_online, heartbeat_online

            fp = collect_machine_fingerprint()
            result = await activate_online(_settings.license_key, fp)
            _lf_logger.info(
                "license_phone_home valid=%s reason=%s",
                result.get("valid"),
                result.get("reason"),
            )
            if (
                not result.get("valid")
                and result.get("reason") == "offline_grace_expired"
            ):
                _lf_logger.critical(
                    "license_offline_grace_expired — paid providers blocked"
                )

            # Periodic heartbeat: the only way a server-side revoke (a refund,
            # a cancelled contract) reaches a running install. It is the ONLY
            # thing the network is used for — the licence itself is checked
            # offline, in `app.licensing.gate`, on every request.
            #
            # This defaulted to 30 seconds, which is 2,880 calls a day from
            # every customer to a single Cloudflare Worker, to answer a
            # question whose answer changes maybe once in a licence's life.
            # Hourly means a revocation lands within the hour; the 7-day
            # offline grace covers the case where we are unreachable.
            interval = max(
                60,
                int(_ph_os.environ.get("ABS_HEARTBEAT_INTERVAL_SECS", "3600")),
            )

            async def _heartbeat_loop(token: str, machine_fp: str, secs: int) -> None:
                while True:
                    try:
                        await asyncio.sleep(secs)
                        hb = await heartbeat_online(token, machine_fp)
                        _lf_logger.info(
                            "license_heartbeat valid=%s reason=%s",
                            hb.get("valid"),
                            hb.get("reason"),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        _lf_logger.warning("heartbeat_loop_error: %s", exc)

            _heartbeat_task = asyncio.create_task(
                _heartbeat_loop(_settings.license_key, fp, interval)
            )
            _lf_logger.info(
                "license heartbeat scheduler started interval=%ds", interval
            )
        except Exception as exc:
            _lf_logger.warning("phone_home_skipped: %s", exc)
    # Load the provider config YAMLs once at boot (idempotent).
    try:
        from app.providers.configs import load_all

        cfg_count = len(load_all())
        if cfg_count:
            _lf_logger.info("provider configs loaded: %d", cfg_count)
    except Exception as exc:
        _lf_logger.warning("provider configs load skipped: %s", exc)

    # The MCP streamable-http session manager accepts exactly one `run()` call.
    # Tests open the lifespan once per fixture, so it is skipped there — the MCP
    # tests assert the mount exists rather than speaking the protocol.
    import os

    if os.environ.get("ABS_TEST_MODE") == "1":
        _lf_logger.warning(
            "⚠️ ABS_TEST_MODE=1 — MCP /mcp session manager, Cerbos pre-warm, "
            "LangFuse and the health monitor are DISABLED. This must NOT be set "
            "in any real/customer deployment: it silently breaks the Claude Code "
            "MCP transport (/mcp → 500). Unset ABS_TEST_MODE for production."
        )
        yield
        return

    # Pre-warm Cerbos PDP client + LangFuse client so the first
    # request doesn't pay the connection cost.
    try:
        from cerbos.sdk.client import CerbosClient

        from app.config import settings as _abs_settings

        _app.state.cerbos_client = CerbosClient(
            _abs_settings.cerbos_host, timeout_secs=2.0
        )
        _lf_logger.info("cerbos pre-warmed host=%s", _abs_settings.cerbos_host)
    except Exception as exc:
        _lf_logger.warning("cerbos pre-warm skipped: %s", exc)

    try:
        from app.observability.langfuse_client import (
            get_langfuse,
            is_enabled as _lf_enabled,
        )

        if _lf_enabled():
            get_langfuse()
            _lf_logger.info("langfuse pre-warmed")
    except Exception as exc:
        _lf_logger.warning("langfuse pre-warm skipped: %s", exc)

    # Start the provider health monitor (skipped in test mode).
    try:
        from app.health.monitor import monitor as _hmon

        _hmon.start()
        _lf_logger.info("health monitor started (interval=%ds)", _hmon.interval)
    except Exception as exc:
        _lf_logger.warning("health monitor start skipped: %s", exc)

    try:
        async with mcp_server.session_manager.run():
            # External MCP federation — re-publish enabled servers' tools into
            # /mcp (no-op unless external_mcp_federate_to_mcp is on). Runs as a
            # detached task so a slow/unreachable upstream cannot delay readiness.
            async def _federate_bg() -> None:
                try:
                    from app.mcp.external.federation import refresh_federation

                    _n = await refresh_federation()
                    if _n:
                        _lf_logger.info(
                            "external MCP federation: %d tool(s) published", _n
                        )
                except Exception as exc:
                    _lf_logger.warning("external MCP federation skipped: %s", exc)

            asyncio.create_task(_federate_bg())
            yield
    finally:
        # Cancel the heartbeat loop before shutdown so a stuck
        # CF Worker call doesn't hold the lifespan-finalisation open.
        if _heartbeat_task is not None:
            _heartbeat_task.cancel()
            try:
                await _heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass

        # Flush LangFuse + close Cerbos pre-warmed client
        try:
            from app.observability.langfuse_client import close_langfuse

            close_langfuse()
        except Exception:
            pass
        try:
            cli = getattr(_app.state, "cerbos_client", None)
            if cli is not None:
                cli.close()
        except Exception:
            pass

        try:
            from app.health.monitor import monitor as _hmon

            await _hmon.stop()
        except Exception:
            pass


from app.config import settings as _app_settings  # noqa: E402

app = FastAPI(title="Automatia ABS", version=_app_settings.version, lifespan=lifespan)
install_rate_limit(app)  # must run before include_router so decorators work

# Convert RLS write-side violations (Postgres SQLSTATE 42501)
# into a typed 403 tenant_isolation_required response. Without this any
# request that tried to insert into an RLS-guarded audit table without a
# matching tenant GUC would surface a generic 500.
from app.middleware.rls_violation_handler import install_rls_violation_handler

install_rls_violation_handler(app)


# Every provider in the chain failed and some may recover. The cascade used to
# raise FastAPI's HTTPException for this — from a library that agents, MCP tools,
# pipelines and background workers all call without any web request in sight, and
# which every one of them was catching `ProviderError` around. Now it raises a
# ProviderError (`CascadeUnavailable`) so those callers degrade instead of dying,
# and the HTTP surface is unchanged: the same 503, the same body, the same
# Retry-After, built here instead of down there.
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402

from app.providers.schemas import CascadeUnavailable as _CascadeUnavailable  # noqa: E402


@app.exception_handler(_CascadeUnavailable)
async def _cascade_unavailable_handler(request, exc: _CascadeUnavailable):  # noqa: ANN001
    return _JSONResponse(
        status_code=503,
        content={"detail": exc.detail()},
        headers={"Retry-After": str(exc.retry_after)},
    )


# X-ABS-Audience enforcement (off by default; helm values flip it on).
from app.config import settings as _abs_settings_for_audience
from app.middleware.audience import install_audience_enforcer

install_audience_enforcer(app, _abs_settings_for_audience)
app.add_middleware(FirstRunMiddleware)
app.add_middleware(I18nMiddleware)
app.add_middleware(DemoModeMiddleware)
# Content-Length cap before any body parse (DoS mitigation).
from app.middleware.body_size_limit import install_body_size_limit

install_body_size_limit(app)
# Pin the request's tenant to the RLS ContextVar so the Postgres
# RLS policies (0015 audit tables + 0019 tenant tables) actually engage in the
# live request path. The policies + GUC listener shipped, but nothing ever
# attached a populator, so the GUC stayed unset outside the postgres_only
# tests. Pure-ASGI so the ContextVar reaches the endpoint + DB session listener;
# inert on SQLite (no RLS engine). Best-effort + fail-open.
from app.middleware.tenant_context import install_tenant_context

install_tenant_context(app)
# Outermost so request_id is set before all other middleware run.
# Starlette wraps LIFO: the last add_middleware call is the outermost.
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router.router)
app.include_router(
    auth_router.claim_v1_router
)  # /v1/auth/magic-claim (SPA /activate page)
app.include_router(oauth_router)  # OAuth 2.1 + PKCE + JWKS
app.include_router(v1_projects_router)  # MCP gateway v1
app.include_router(v1_rag_router)  # RAG ingest/query
app.include_router(v1_agents_router)  # Agentic Growth — Agent Registry + Runtime
app.include_router(v1_approvals_router)  # Agentic Growth — Approval Center
app.include_router(v1_inbound_router)  # Agentic Growth — Inbound + Knowledge MVP
app.include_router(v1_dashboard_router)  # Agentic Growth — Growth Dashboard
app.include_router(v1_leads_router)  # Agentic Growth — Lead Intelligence
app.include_router(v1_context_graph_router)  # Agentic Growth — Context Graph + ER
app.include_router(v1_connectors_router)  # Agentic Growth — Connector Marketplace
app.include_router(v1_agentic_wf_router)  # Agentic Growth — Workflow Designer
app.include_router(v1_consent_router)  # Agentic Growth — Consent Ledger
app.include_router(admin_auth_router.router)
app.include_router(admin_dashboard_router.router)
app.include_router(admin_analytics_router.router)
app.include_router(admin_licenses_router.router)
app.include_router(admin_churn_router.router)
app.include_router(admin_errors_router.router)
app.include_router(admin_audit_router.router)
app.include_router(admin_users_router.router)  # /v1/admin/users
app.include_router(admin_usage_router.router)  # /v1/admin/usage
app.include_router(admin_widget_pricing_router.router)  # /v1/admin/widget_pricing
app.include_router(admin_providers_status_router.router)  # /v1/admin/providers/status
app.include_router(admin_tenant_router.router)  # /v1/admin/tenant + /v1/admin/branding
app.include_router(admin_providers_save_router.router)  # POST /v1/admin/providers/{id}
app.include_router(
    admin_provider_keys_router.router
)  # MT Phase 1 — /v1/admin/provider-keys
app.include_router(admin_projects_router.router)  # MT Phase 1 — /v1/admin/projects
app.include_router(admin_settings_store_router.router)  # /v1/admin/settings/{section}
app.include_router(beta_portal_router.router)
app.include_router(beta_admin_router.router)
app.include_router(demo_mode_router.router)
app.include_router(panel_tools_router.router)
app.include_router(panel_cascade_router.router)
app.include_router(panel_pipeline_router.router)
app.include_router(license_router.router)
app.include_router(checkout_router.router)
app.include_router(billing_portal_router.router)
app.include_router(demo_admin_router.router)
app.include_router(vault_admin_router.router)
app.include_router(setup_router.router)
app.include_router(smart_link_router.router)
app.include_router(slack_router.router)
app.include_router(slack_router.events_router)  # 028 signed webhook
app.include_router(github_app_router.router)  # 028 GitHub App webhook
app.include_router(status_page_router.router)
app.include_router(secrets_router.router)
app.include_router(update_router.router)
app.include_router(stripe_webhook_router.router)
app.include_router(stream_router.router)
app.include_router(symbol_graph_router.router)
app.include_router(quota_router.router)
app.include_router(graph_router.router)  # /v1/graph
app.include_router(graph_rag_router.router)  # GraphRAG — /v1/graph-rag
app.include_router(system_quota_router.router)
app.include_router(system_feature_usage_router.router)  # S20.3
app.include_router(marketplace_router.router)
app.include_router(meetings_router.router)  # S20.4
app.include_router(workflows_router.router)  # P1 S19 close
app.include_router(cascade_router.router)  # /v1/cascade/*
app.include_router(chat_router.router)  # /v1/chat/*
app.include_router(agent_caps_router.router)  # what agent mode may do
app.include_router(mcp_tokens_router.router)  # /v1/mcp/tokens
from app.api import external_mcp as external_mcp_router  # External MCP federation

app.include_router(external_mcp_router.router)  # /v1/admin/external-mcp (flag-gated)
app.include_router(cc_hooks_router.router)  # /v1/hooks/*
app.include_router(transcribe_router.router)  # S20.2
app.include_router(tts_router.router)  # S20.1
app.include_router(disagreement_router.router)
app.include_router(email_unsubscribe_router.router)
app.include_router(health_full_router.router)
app.include_router(hooks_router.router)
app.include_router(me_account_router.router)
app.include_router(me_audit_router.router)
app.include_router(me_consent_router.router)
app.include_router(me_data_export_router.router)
app.include_router(panel_router.router)

# Setup wizard static assets
app.mount(
    "/setup/assets",
    StaticFiles(directory=str(SETUP_STATIC_DIR / "assets")),
    name="setup-assets",
)

# Static fallback — /static/* serves what is left under app/static/:
# the setup wizard, connect.html and status.html.
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static"), html=True),
    name="static",
)


@app.get("/setup", include_in_schema=False)
async def setup_index():
    """Setup wizard UI (vanilla HTML/JS)."""
    return FileResponse(SETUP_STATIC_DIR / "index.html", media_type="text/html")


# Brief 4 R4 — vanilla 032 admin route deleted; /admin/* is now Next.js
# territory served by the `landing` container behind the Caddy split.
# Keeping the static mount so /static/* (panel, setup) still works.


# MCP HTTP transport — Claude Code `claude mcp add abs https://abs.local/mcp`
# Wrapped in McpTokenAuthASGI so the minted abs_mcp_ bearer token is enforced
# on every transport request (FastMCP ships no auth of its own). Pure-ASGI so
# the streamable-HTTP/SSE responses are not buffered/broken.
from app.mcp.transport_auth import McpTokenAuthASGI  # noqa: E402

if not getattr(_app_settings, "mcp_auth_enforce", True):
    import logging as _mcp_auth_log

    _mcp_auth_log.getLogger("app.mcp.transport_auth").warning(
        "⚠️ ABS_MCP_AUTH_ENFORCE=false — the /mcp transport will serve ALL "
        "tools to ANY caller that passes the host allowlist, with no per-user "
        "token. Only acceptable on a trusted, network-isolated dev box. Set "
        "ABS_MCP_AUTH_ENFORCE=true (default) for any reachable deployment."
    )
app.mount("/mcp", McpTokenAuthASGI(mcp_http_app()))

# Inngest durable workflow engine. Functions are auto-discovered by the
# Inngest dev server (`npx inngest-cli@latest dev`) via /api/inngest.
try:
    from inngest import fast_api as _inngest_fastapi

    from app.worker.inngest_app import functions as _inngest_functions
    from app.worker.inngest_app import inngest_client as _inngest_client

    _inngest_fastapi.serve(app, _inngest_client, _inngest_functions)
except Exception as _exc:  # pragma: no cover — keep boot resilient if SDK absent
    import logging as _logging

    _logging.getLogger(__name__).warning("inngest serve skipped: %s", _exc)


def _healthz_db_ready() -> bool:
    """Fast `SELECT 1` readiness ping; any failure swallowed into a False."""
    import logging

    from sqlalchemy import text

    try:
        with get_engine().connect() as conn:
            return conn.execute(text("SELECT 1")).scalar() == 1
    except Exception:
        logging.getLogger(__name__).warning("healthz db ping failed", exc_info=True)
        return False


@app.get("/healthz")
def healthz(response: Response):
    """Readiness probe wired to the container/orchestrator healthcheck.

    Verifies the one dependency without which the backend cannot serve a
    single real request — the database. The previous always-"ok" body let
    docker/k8s keep a backend with a dead DB marked healthy (traffic routed,
    never restarted); the customer compose healthcheck comment even promised
    a DB gate this handler never implemented. Kept cheap: one `SELECT 1`,
    any failure degraded to a 503 (not a 500) so the probe stays well-behaved.
    """
    if not _healthz_db_ready():
        response.status_code = 503
        return {"status": "degraded", "service": "abs-backend", "db": "down"}
    return {"status": "ok", "service": "abs-backend", "db": "up"}
