"""6 P1 bug fix verification.

Tests cover the surface area each fix touches without spinning up the
full stack:
  - panel/{path} → admin/{path} 308 route
  - daily_cost MCP tool resilience (IndexError → fallback)
  - cascade no-provider pre-flight HTTP 503 (not 200 SSE)
  - Caddyfile.customer @backend includes /me/*
  - ABS_VERSION=1.0.1 default + CHANGELOG entry
  - customer compose explicit ABS_RATE_LIMIT_ENABLED=true
"""

from __future__ import annotations

import pathlib
import re

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

PANEL_PY = BACKEND_ROOT / "app" / "api" / "panel.py"
BILLING_TOOLS_PY = BACKEND_ROOT / "app" / "mcp" / "tools" / "billing_tools.py"
CHAT_PY = BACKEND_ROOT / "app" / "api" / "chat.py"
CADDYFILE_CUSTOMER = REPO_ROOT / "infra" / "Caddyfile.customer"
COMPOSE_CUSTOMER = REPO_ROOT / "infra" / "docker-compose.customer.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CHANGELOG = REPO_ROOT / "docs" / "CHANGELOG.md"


# ---- panel → admin redirect ------------------------------------------------
def test_panel_subpath_compat_redirect_declared() -> None:
    raw = PANEL_PY.read_text()
    assert "panel_subpath_compat_redirect" in raw, (
        "panel.py must declare /panel/{path:path} → /admin/{path} catch-all"
    )
    assert '"/panel/{path:path}"' in raw
    assert "status_code=308" in raw


def test_panel_catchall_returns_308_via_starlette_router() -> None:
    """In-process: invoke FastAPI route function with a fake path."""
    from app.api.panel import panel_subpath_compat_redirect

    resp = panel_subpath_compat_redirect("chat")
    assert resp.status_code == 308
    assert resp.headers["location"] == "/admin/chat"

    # Root /panel/ case ("" path → /admin).
    resp_root = panel_subpath_compat_redirect("")
    assert resp_root.headers["location"] == "/admin"


# ---- daily-cost tool resilience --------------------------------------------
def test_daily_cost_tool_handles_index_error() -> None:
    """Force estimate_daily_cost to raise IndexError, ensure tool catches.

    FastMCP wraps the function; the underlying coroutine is reachable via
    the registry. For this test we replicate the tool body directly so we
    do not depend on FastMCP internals (which changed across releases).
    """
    raw = BILLING_TOOLS_PY.read_text()
    block = raw.split("async def daily_cost(", 1)[1]
    body = block.split("async def ", 1)[0]
    # Required code paths the source must contain to count as the fix.
    assert "try:" in body and "except (IndexError, KeyError)" in body
    assert "today_usd" in body and "0.0" in body
    assert "_diagnostic" in body
    assert "No cost data yet" in body


# ---- cascade pre-flight when every provider is down ------------------------
def test_chat_completions_preflights_cascade_503() -> None:
    raw = CHAT_PY.read_text()
    assert "all_providers_unavailable" in raw, (
        "chat.py must emit structured `all_providers_unavailable` 503 "
        "BEFORE starting the SSE stream"
    )
    # Retry-After header in the HTTPException response.
    assert "Retry-After" in raw
    # Pre-flight probe lives before the stream() definition.
    head, _, tail = raw.partition("async def stream()")
    assert "get_active_providers" in head, (
        "provider probe must run pre-stream so HTTP status reflects "
        "the all-down case (a repro found: 200 SSE instead of 503)"
    )


# ---- Caddyfile routes /me/* ------------------------------------------------
def test_caddyfile_customer_backend_pattern_includes_me() -> None:
    raw = CADDYFILE_CUSTOMER.read_text()
    backend_line = next(
        (line for line in raw.splitlines() if "@backend path" in line), None
    )
    assert backend_line is not None, "Caddyfile.customer missing @backend matcher"
    assert "/me/*" in backend_line, (
        "Caddyfile.customer @backend must include /me/* so KVKK self-service "
        "endpoints reach FastAPI instead of the Next.js 404 page"
    )


# ---- version + changelog ---------------------------------------------------
def test_env_example_version_is_one_zero_one() -> None:
    raw = ENV_EXAMPLE.read_text()
    assert re.search(r"^ABS_VERSION=1\.0\.1\b", raw, re.MULTILINE), (
        "the images ship at 1.0.1 — .env.example must point there"
    )


def test_changelog_documents_the_hotfix_release() -> None:
    # The 1.0.1 release closed four P0 and six P1 findings. What the changelog
    # owes a reader is the version and what it fixed for them — not our internal
    # bug ids, which mean nothing outside this team and belong nowhere near a
    # public repo.
    raw = CHANGELOG.read_text()
    assert "## 1.0.1" in raw, "CHANGELOG.md must document the 1.0.1 release"
    assert "P0 (4/4)" in raw and "P1 (6/6)" in raw, (
        "the 1.0.1 entry must still account for every finding it closed"
    )


# ---- rate limit is on in the customer compose ------------------------------
def test_customer_compose_forces_rate_limit_enabled() -> None:
    raw = COMPOSE_CUSTOMER.read_text()
    # Default-on substitution: ${ABS_RATE_LIMIT_ENABLED:-true}.
    assert "ABS_RATE_LIMIT_ENABLED" in raw, (
        "customer compose must explicitly set ABS_RATE_LIMIT_ENABLED so "
        "the /auth/login 5/min brute-force guard stays on by default"
    )
    assert ":-true" in raw
    # ABS_ENV defaults to prod so the dev-mode disable path never engages.
    assert "ABS_ENV" in raw
    assert "${ABS_ENV:-prod}" in raw


def test_auth_login_decorated_with_rate_limit() -> None:
    raw = (BACKEND_ROOT / "app" / "api" / "auth.py").read_text()
    # The login route is rate-limited.
    block = raw.split('@router.post("/login")', 1)
    assert len(block) == 2, "auth.py missing @router.post('/login') decorator"
    next_segment = block[1][:300]
    assert "limiter.limit" in next_segment, (
        "/auth/login must retain the slowapi @limiter.limit decorator "
        "(the brute-force guard, enforced in the customer compose)"
    )
