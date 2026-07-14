"""OAuth pen-test scaffolding.

These tests live OUTSIDE the main pytest tree (security_tests/) so external
researchers can run them against staging without spinning up the in-process
TestClient. Each test is a placeholder that exercises one threat from
docs/security/oauth_pentest.md against an `httpx.AsyncClient` pointed at the
staging URL via the ABS_STAGING_URL env var.

Wire the fixtures (e.g. `async_client`, `valid_authcode`) when running.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import httpx
import pytest

STAGING_URL = os.environ.get(
    "ABS_STAGING_URL", "https://staging.abs-server.example.com"
)


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=STAGING_URL, timeout=10.0) as client:
        yield client


@pytest.mark.asyncio
async def test_pkce_plain_rejected(async_client: httpx.AsyncClient) -> None:
    params = {
        "response_type": "code",
        "client_id": "test-client",
        "redirect_uri": "https://client.example.com/cb",
        "code_challenge": "plainchallenge",
        "code_challenge_method": "plain",
        "scope": "openid profile",
        "state": "xyz",
    }
    resp = await async_client.get("/oauth/authorize", params=params)
    assert resp.status_code in (400, 403)
    body = resp.json()
    assert body.get("error") in {"invalid_request", "unsupported_challenge_method"}


@pytest.mark.asyncio
async def test_refresh_token_single_use(async_client: httpx.AsyncClient) -> None:
    # TODO: wire a valid auth-code fixture; placeholder for the runbook.
    refresh_token = os.environ.get("ABS_TEST_REFRESH_TOKEN", "")
    if not refresh_token:
        pytest.skip("ABS_TEST_REFRESH_TOKEN not set")
    first = await async_client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    assert first.status_code == 200
    second = await async_client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    assert second.status_code in (400, 401)
    assert second.json().get("error") == "invalid_grant"


@pytest.mark.asyncio
async def test_jwks_signature_validates(async_client: httpx.AsyncClient) -> None:
    jwks_resp = await async_client.get("/.well-known/jwks.json")
    assert jwks_resp.status_code == 200
    keys = jwks_resp.json().get("keys", [])
    assert keys, "JWKS must publish at least one key"
    for key in keys:
        assert key.get("kty") == "RSA"
        assert key.get("kid")
        assert key.get("n")
        assert key.get("e")


@pytest.mark.asyncio
async def test_audience_enforced_on_v1(async_client: httpx.AsyncClient) -> None:
    token = os.environ.get("ABS_TEST_ACCESS_TOKEN", "")
    if not token:
        pytest.skip("ABS_TEST_ACCESS_TOKEN not set")

    # Missing audience header → 400
    r1 = await async_client.get(
        "/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 400

    # Wrong audience → 400
    r2 = await async_client.get(
        "/v1/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "X-ABS-Audience": "wrong-audience",
        },
    )
    assert r2.status_code == 400
