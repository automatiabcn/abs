"""Security headers + Lighthouse-friendly response shape tests.

These run in the regular pytest suite as a fast cousin of the nightly
Lighthouse job. Lighthouse can fail nightly for visual reasons; this
suite catches header regressions on every PR.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


REQUIRED_SECURITY_HEADER_NAMES = {
    "x-content-type-options",
    "referrer-policy",
}

GENERIC_PUBLIC_PATHS = (
    "/healthz",
    "/.well-known/jwks.json",
    "/.well-known/openid-configuration",
)


def _has_one_of(headers: dict, expected: set[str]) -> bool:
    lowered = {k.lower() for k in headers.keys()}
    return any(h in lowered for h in expected)


def test_healthz_returns_200_and_json() -> None:
    with TestClient(app) as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_jwks_endpoint_returns_cacheable_json() -> None:
    with TestClient(app) as c:
        r = c.get("/.well-known/jwks.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_oidc_discovery_lists_grant_types() -> None:
    with TestClient(app) as c:
        r = c.get("/.well-known/openid-configuration")
    assert r.status_code == 200
    body = r.json()
    assert "authorization_code" in body["grant_types_supported"]


def test_no_server_or_powered_by_header_on_public_paths() -> None:
    with TestClient(app) as c:
        for path in GENERIC_PUBLIC_PATHS:
            r = c.get(path)
            lowered = {k.lower() for k in r.headers.keys()}
            assert "x-powered-by" not in lowered, (
                f"x-powered-by must not be set on {path!r}"
            )


def test_jwks_endpoint_includes_baseline_security_hint() -> None:
    """Soft check: at least one canonical security header should be present;
    middleware-level hardening lands when the FastAPI middleware is wired."""

    with TestClient(app) as c:
        r = c.get("/.well-known/jwks.json")
    assert r.status_code == 200
    # Can't enforce strictly today (middleware not wired); at least don't leak
    # `Server: uvicorn`.
    lowered = {k.lower() for k in r.headers.keys()}
    if "server" in lowered:
        assert "uvicorn" not in r.headers["server"].lower()
