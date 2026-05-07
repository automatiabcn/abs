from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth as auth_router
from app.api.v1.projects import router as v1_projects_router
from app.api.v1.rag import router as v1_rag_router
from app.auth.oauth.routes import router as oauth_router
from app.api import beta_admin as beta_admin_router
from app.api import beta_portal as beta_portal_router
from app.api import billing_portal as billing_portal_router
from app.api.admin import analytics_licenses as admin_analytics_router
from app.api.admin import audit_recent as admin_audit_router
from app.api.admin import auth as admin_auth_router
from app.api.admin import churn as admin_churn_router
from app.api.admin import dashboard as admin_dashboard_router
from app.api.admin import errors_recent as admin_errors_router
from app.api.admin import usage as admin_usage_router  # BUG-V1 — /v1/admin/usage
from app.api.admin import users as admin_users_router  # Q8.5 finalize — /v1/admin/users
from app.api.admin import widget_pricing as admin_widget_pricing_router  # Q12-R84
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
from app.api import cascade as cascade_router            # Q4 P10 — /v1/cascade/*
from app.api import chat as chat_router                  # Q8 Phase A — /v1/chat/*
from app.api import mcp_tokens as mcp_tokens_router      # Q8 Phase N — /v1/mcp/tokens
from app.api import claude_code_hooks as cc_hooks_router # Q8 Phase P — /v1/hooks/*
from app.api import marketplace as marketplace_router  # CJ-008 — /v1/marketplace/*
from app.api import meetings as meetings_router          # S20.4 — /v1/meetings
from app.api import workflows as workflows_router        # P1 S19 — /v1/workflows
from app.api import graph as graph_router  # Q7 Phase A — /v1/graph
from app.api import quota as quota_router
from app.api.system import quota as system_quota_router  # CJ-009 — /v1/system/quota_status
from app.api.system import feature_usage as system_feature_usage_router  # S20.3
from app.api import transcribe as transcribe_router      # S20.2
from app.api import tts as tts_router                    # S20.1
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
from app.db.session import init_db
from app.mcp.server import http_app as mcp_http_app
from app.mcp.server import mcp_server
from app.middleware.demo_mode import DemoModeMiddleware
from app.middleware.first_run import FirstRunMiddleware
from app.middleware.i18n import I18nMiddleware
from app.middleware.rate_limit import install_rate_limit, limiter
from app.middleware.request_id import RequestIDMiddleware  # Q12-L23

PANEL_STATIC_DIR = Path(__file__).resolve().parent / "static" / "panel"
SETUP_STATIC_DIR = Path(__file__).resolve().parent / "static" / "setup"
# Brief 4 R4 — ADMIN_STATIC_DIR removed; /admin/* is Next.js territory
# served by the `landing` container behind the Caddy route split.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import logging

    init_db()
    _lf_logger = logging.getLogger("app.lifespan")

    # 013 — vault: plaintext .env migration + boot decrypt → settings'e bind
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

    # BUG-V3 — Detect ABS_ANTHROPIC_ENABLED opt-in flips and emit
    # a SOC2 audit row (PROMISE.md "every opt-in flip ... audit log").
    try:
        from app.config import settings as _optin_settings
        from app.observability.optin_state import detect_and_emit_flip

        detect_and_emit_flip(current_enabled=bool(_optin_settings.anthropic_enabled))
    except Exception as exc:
        _lf_logger.warning("optin flip detection skipped: %s", exc)

    # 011 — lisans yoksa demo başlat (idempotent)
    from app.config import settings as _settings

    if not _settings.license_key:
        try:
            from app.licensing.demo import start_demo

            start_demo()
        except Exception:
            pass
    # 014 — provider configs YAML yükle (boot, idempotent)
    try:
        from app.providers.configs import load_all

        cfg_count = len(load_all())
        if cfg_count:
            _lf_logger.info("provider configs loaded: %d", cfg_count)
    except Exception as exc:
        _lf_logger.warning("provider configs load skipped: %s", exc)

    # MCP streamable-http session manager tek sefer `run()` çağrısı kabul eder.
    # TestClient her fixture'da lifespan açtığı için testlerde skip ediyoruz
    # (zaten /mcp endpoint'i testlerinde gerçek protokol yerine sadece mount varlığı
    # kontrol ediliyor).
    import os

    if os.environ.get("ABS_TEST_MODE") == "1":
        yield
        return

    # T-018 — pre-warm Cerbos PDP client + LangFuse client so the first
    # request doesn't pay the connection cost (closes T-005 caveat).
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

    # 014 — health monitor başlat (test_mode skip)
    try:
        from app.health.monitor import monitor as _hmon

        _hmon.start()
        _lf_logger.info("health monitor started (interval=%ds)", _hmon.interval)
    except Exception as exc:
        _lf_logger.warning("health monitor start skipped: %s", exc)

    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        # T-018 — flush LangFuse + close Cerbos pre-warmed client
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


app = FastAPI(title="Automatia ABS", version="0.1.0", lifespan=lifespan)
install_rate_limit(app)  # 028 — must run before include_router so decorators work

# T-058 caveat #11 — X-ABS-Audience enforcement (off by default; helm values flip it on).
from app.config import settings as _abs_settings_for_audience
from app.middleware.audience import install_audience_enforcer

install_audience_enforcer(app, _abs_settings_for_audience)
app.add_middleware(FirstRunMiddleware)
app.add_middleware(I18nMiddleware)
app.add_middleware(DemoModeMiddleware)
# Q12-L25 sweep 3 — Content-Length cap before any body parse (DoS mitigation).
from app.middleware.body_size_limit import install_body_size_limit

install_body_size_limit(app)
# Q12-L23 — outermost so request_id is set before all other middleware run.
# Starlette wraps LIFO: the last add_middleware call is the outermost.
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router.router)
app.include_router(oauth_router)  # T-003 — OAuth 2.1 + PKCE + JWKS
app.include_router(v1_projects_router)  # T-005 — MCP gateway v1
app.include_router(v1_rag_router)       # T-011 — RAG ingest/query
app.include_router(admin_auth_router.router)
app.include_router(admin_dashboard_router.router)
app.include_router(admin_analytics_router.router)
app.include_router(admin_churn_router.router)
app.include_router(admin_errors_router.router)
app.include_router(admin_audit_router.router)
app.include_router(admin_users_router.router)  # Q8.5 finalize — /v1/admin/users
app.include_router(admin_usage_router.router)  # BUG-V1 — /v1/admin/usage
app.include_router(admin_widget_pricing_router.router)  # Q12-R84 — /v1/admin/widget_pricing
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
app.include_router(graph_router.router)        # Q7 Phase A — /v1/graph
app.include_router(system_quota_router.router)  # CJ-009
app.include_router(system_feature_usage_router.router)  # S20.3
app.include_router(marketplace_router.router)   # CJ-008
app.include_router(meetings_router.router)      # S20.4
app.include_router(workflows_router.router)     # P1 S19 close
app.include_router(cascade_router.router)       # Q4 P10 — /v1/cascade/*
app.include_router(chat_router.router)          # Q8 Phase A — /v1/chat/*
app.include_router(mcp_tokens_router.router)    # Q8 Phase N — /v1/mcp/tokens
app.include_router(cc_hooks_router.router)      # Q8 Phase P — /v1/hooks/*
app.include_router(transcribe_router.router)    # S20.2
app.include_router(tts_router.router)           # S20.1
app.include_router(disagreement_router.router)
app.include_router(email_unsubscribe_router.router)
app.include_router(health_full_router.router)
app.include_router(hooks_router.router)
app.include_router(me_account_router.router)
app.include_router(me_audit_router.router)
app.include_router(me_consent_router.router)
app.include_router(me_data_export_router.router)
app.include_router(panel_router.router)

# panel asset'leri (css/js/img) — /panel/login ve /panel route'larıyla çakışmaz,
# StaticFiles fallback sadece /panel/assets/* için match eder.
app.mount(
    "/panel/assets",
    StaticFiles(directory=str(PANEL_STATIC_DIR / "assets")),
    name="panel-assets",
)

# 012 — Setup wizard static assets
app.mount(
    "/setup/assets",
    StaticFiles(directory=str(SETUP_STATIC_DIR / "assets")),
    name="setup-assets",
)

# Demo / staticfile fallback — /static/* tüm app/static/ dosyalarını serve eder
# (admin/index.html, panel/tools.html, connect.html vb.)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static"), html=True),
    name="static",
)


@app.get("/setup", include_in_schema=False)
async def setup_index():
    """012 — Setup wizard UI (vanilla HTML/JS)."""
    return FileResponse(SETUP_STATIC_DIR / "index.html", media_type="text/html")


# Brief 4 R4 — vanilla 032 admin route deleted; /admin/* is now Next.js
# territory served by the `landing` container behind the Caddy split.
# Keeping the static mount so /static/* (panel, setup) still works.


# MCP HTTP transport — Claude Code `claude mcp add abs https://abs.local/mcp`
app.mount("/mcp", mcp_http_app())

# T-002 — Inngest durable workflow engine. Functions are auto-discovered by the
# Inngest dev server (`npx inngest-cli@latest dev`) via /api/inngest.
try:
    from inngest import fast_api as _inngest_fastapi

    from app.worker.inngest_app import functions as _inngest_functions
    from app.worker.inngest_app import inngest_client as _inngest_client

    _inngest_fastapi.serve(app, _inngest_client, _inngest_functions)
except Exception as _exc:  # pragma: no cover — keep boot resilient if SDK absent
    import logging as _logging

    _logging.getLogger(__name__).warning("inngest serve skipped: %s", _exc)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "abs-backend"}


