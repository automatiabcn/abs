# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What someone with the URL and no account can read.

ABS is self-hosted, so "the URL" is a real thing a stranger can have: a company
puts the server on a domain, and everything not behind a login is behind nothing.
Four routes were, and every one of them answered a question about the company:

* `/v1/panel/tools` — the whole capability catalogue, and once an external MCP
  server is connected, `ext_<slug>__*` names that read out the internal systems
  it is wired into.
* `/v1/panel/cascade/recent` — which providers are in use, and a timestamp for
  every tool call, which is a diary of when the company works.
* `/v1/panel/pipeline/recent` — the same for pipeline runs.
* `/v1/system/quota_status` — allowance burned per provider, and which providers
  are configured at all. Its near-twin `/v1/quota/status` was behind a login the
  entire time, which is the tell: nobody decided this should be open.

Each one sat behind a page that *was* behind a login, which is how they stayed
open — the panel looked gated, and the API under it was not.

The last test here is the one that matters in a year: it walks the live route
table and fails on any *new* route that ships without a guard. The allow-list is
the set of things that are public on purpose — the setup wizard before an admin
exists, signed webhooks, OAuth callbacks, licence activation, health. Adding to
it should feel like a decision, because it is one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

CLOSED_NOW = [
    ("GET", "/v1/panel/tools"),
    ("GET", "/v1/panel/cascade/recent"),
    ("GET", "/v1/panel/pipeline/recent"),
    ("GET", "/v1/system/quota_status"),
]


@pytest.fixture()
def anon() -> TestClient:
    """A client with no cookie and no bearer — a stranger with the URL."""
    return TestClient(app)


@pytest.mark.parametrize("method,path", CLOSED_NOW)
def test_a_stranger_gets_nothing_from_the_operator_routes(anon, method, path):
    resp = anon.request(method, path)
    assert resp.status_code in (401, 403), (
        f"{method} {path} answered {resp.status_code} to a caller with no "
        f"account: {resp.text[:200]}"
    )


def test_the_tool_catalogue_does_not_leak_before_the_login(anon):
    """The specific thing that used to come back: 120 tools, named."""
    resp = anon.get("/v1/panel/tools")
    assert resp.status_code in (401, 403)
    body = resp.text
    # No catalogue, and no shape of one either.
    assert "ask_" not in body
    assert "category_counts" not in body


def test_the_signed_in_operator_still_gets_the_catalogue(anon):
    """Closing a door on a stranger is only correct if it still opens for the
    operator. Without this, 'nobody can read it' passes by breaking the page."""
    from app.api.auth import current_admin

    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    try:
        resp = anon.get("/v1/panel/tools")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["total"] > 0
        assert payload["tools"], "the operator got an empty catalogue"
    finally:
        app.dependency_overrides.clear()


# Answers a stranger is *meant* to get. Each is reachable before anyone has an
# account, or is called by something that is not a person:
#   - the setup wizard runs on a server with no admin yet (and `step_admin` 409s
#     once one exists — that is covered in test_audit_0713_hardening.py);
#   - health, status and update checks exist to be probed;
#   - licence status is how a server reports whether it is licensed at all;
#   - the marketplace listing is a catalogue of what you *could* install, not of
#     anything this company has;
#   - demo-mode status is a banner flag.
#
# Everything else must refuse. Note what is deliberately NOT here: nothing that
# reports what this company has configured, used, connected or done.
_STRANGER_MAY_READ = {
    "/v1/status",
    "/v1/health/full",
    "/v1/update/check",
    "/v1/demo-mode/status",
    "/v1/license/status",
    "/v1/license/info",
    "/v1/license/demo-status",
    "/v1/marketplace/plugins",
    "/v1/setup/status",
    "/v1/system/feature_usage",
    # Static: which integrations ABS *supports*, and the connect page itself,
    # whose every action needs an admin token before it does anything. Neither
    # says a word about what this company has connected — that is
    # `/connected-services`, which is behind the admin check.
    "/v1/smart-link/providers",
    "/v1/smart-link/connect",
}


def test_no_route_hands_a_stranger_data_it_should_not_have():
    """Ask, as a stranger, and see what answers.

    A previous version of this test read the route table looking for a missing
    `Depends(...)`, and flagged fifty routes that check their bearer token inside
    the function body — which is fine, and which no one would have kept. So it
    does the honest thing instead: it calls them.

    Only parameter-free GETs, because those are the ones a stranger can trivially
    hit with a URL bar and no knowledge of the system, which is exactly the threat
    being modelled. A 200 from any of them, unless it is on the list above, means
    a company's server is telling strangers about itself.
    """
    client = TestClient(app)
    leaking: list[str] = []

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not path.startswith("/v1/") or "GET" not in methods:
            continue
        if "{" in path or path in _STRANGER_MAY_READ:
            continue
        resp = client.get(path)
        if resp.status_code == 200:
            leaking.append(f"GET {path} -> 200 {resp.text[:120]}")

    assert leaking == [], (
        "a caller with no account got a 200 out of these — either require a "
        "login, or add the path to _STRANGER_MAY_READ with a reason it is safe "
        "for the whole internet to read:\n  " + "\n  ".join(sorted(leaking))
    )


# --------------------------------------------------------------------------
# Writes.
#
# The sweep above only asks parameter-free GETs, because that is what a URL bar
# can do. It is also why `POST /v1/smart-link/api-key` shipped with no check at
# all and stayed that way: nothing here ever looked at a POST. A write cannot be
# swept by calling it — a handler that checks its token in the body answers 422
# to an empty request before it gets as far as refusing — so this one reads the
# route table instead, and asks a narrower question than "is it safe": does this
# route take a credential from anywhere at all.
#
# A route passes if a known guard is in its dependency tree, or if it declares
# an `Authorization` header. Everything else must be named below, with the
# reason a caller with no account is allowed to reach it.
# --------------------------------------------------------------------------

_GUARDS = {
    "get_auth_context",
    "get_admin_or_bearer_auth_context",
    "admin_required",
    "admin_dep",
    "current_admin",
    "_auth_dependency",
}

_STRANGER_MAY_WRITE = {
    # Signing in is how a stranger stops being one.
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/v1/admin/login"),
    ("POST", "/oauth/token"),
    ("POST", "/auth/device/start"),
    ("POST", "/auth/device/poll"),
    # Public by design, and must not touch an account that already exists
    # (test_signup_cannot_take_an_existing_account.py).
    ("POST", "/auth/signup"),
    # Authenticated inside the handler, from the request itself: the session
    # cookie for the first, the editor's bearer token for the second.
    ("POST", "/auth/device/approve"),
    ("POST", "/v1/editor/chat/stream"),
    # Called by a machine that proves itself with a signature over the body.
    ("POST", "/v1/integrations/github/webhook"),
    ("POST", "/v1/integrations/slack/webhook"),
    ("POST", "/webhooks/stripe"),
    ("POST", "/api/inngest"),
    ("PUT", "/api/inngest"),
    # The setup wizard runs before any admin exists. Each step refuses once
    # setup is complete, and step 1 refuses as soon as an admin exists.
    ("POST", "/v1/setup/lang"),
    ("POST", "/v1/setup/reset"),
    ("POST", "/v1/setup/step/admin"),
    ("POST", "/v1/setup/step/license"),
    ("POST", "/v1/setup/step/domain"),
    ("POST", "/v1/setup/step/anthropic"),
    ("POST", "/v1/setup/step/providers"),
    ("POST", "/v1/setup/step/test"),
    ("POST", "/v1/setup/test"),
    # The storefront: asking for a beta seat, and starting a checkout.
    ("POST", "/v1/beta/request"),
    ("POST", "/v1/checkout/create-session"),
    # The licence key is the credential: it only activates if its signature
    # verifies against the vendor key.
    ("POST", "/v1/license/activate"),
    # Tolerable while billing is switched off, not right. It returns a billing
    # portal link to whoever names the customer's email; before Stripe goes
    # live it should send that link to the address instead of handing it back.
    ("POST", "/v1/billing/portal"),
}


def _takes_a_credential(route) -> bool:
    def guards(dependant) -> bool:
        for dep in dependant.dependencies:
            if getattr(dep.call, "__name__", "") in _GUARDS or guards(dep):
                return True
        return False

    headers = {p.name for p in route.dependant.header_params}
    return "authorization" in headers or guards(route.dependant)


def test_no_write_ships_without_a_credential_or_a_reason():
    from fastapi.routing import APIRoute

    writes = {"POST", "PUT", "PATCH", "DELETE"}
    unguarded: list[str] = []
    seen: set[tuple[str, str]] = set()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods & writes):
            seen.add((method, route.path))
            if (method, route.path) in _STRANGER_MAY_WRITE:
                continue
            if not _takes_a_credential(route):
                unguarded.append(f"{method} {route.path}")

    assert unguarded == [], (
        "these routes change something and take no credential — add the guard, "
        "or add the route to _STRANGER_MAY_WRITE with the reason a caller with "
        "no account may reach it:\n  " + "\n  ".join(sorted(unguarded))
    )

    # An allow-list that outlives its routes is a list of doors nobody checks.
    stale = sorted(_STRANGER_MAY_WRITE - seen)
    assert stale == [], (
        f"_STRANGER_MAY_WRITE names routes that no longer exist: {stale}"
    )


def test_the_write_sweep_would_have_caught_the_api_key_route():
    """The check is only worth having if it fails on the bug it was written for."""
    from fastapi import APIRouter
    from fastapi.routing import APIRoute

    probe = APIRouter()

    @probe.post("/v1/smart-link/api-key-as-it-was")
    async def store_api_key_unguarded(body: dict) -> dict:  # pragma: no cover
        return {"stored": True}

    route = next(r for r in probe.routes if isinstance(r, APIRoute))
    assert _takes_a_credential(route) is False
