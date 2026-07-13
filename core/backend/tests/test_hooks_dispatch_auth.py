# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Security — /v1/hooks/dispatch + /test must require a bearer token.

These run the hook dispatcher and are reachable through Caddy (@backend path
/v1/*), but were mounted on an unauthenticated router while the sibling
/v1/hooks/{quota-check,audit-log,session-start} endpoints were token-gated.
Bring them to parity (same bearer+scope dependency).
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "CHANGEME"}
    )
    assert r.status_code == 200, r.text
    return client


@pytest.mark.parametrize("path", ["/v1/hooks/dispatch", "/v1/hooks/test"])
def test_dispatch_requires_bearer(client, path):
    r = client.post(path, json={"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("path", ["/v1/hooks/dispatch", "/v1/hooks/test"])
def test_dispatch_accepts_hooks_token(admin_client, path):
    minted = admin_client.post(
        "/v1/mcp/tokens", json={"label": "disp", "scope": "hooks", "ttl_days": 1}
    ).json()["token"]
    r = admin_client.post(
        path,
        json={"tool_name": "Bash", "tool_input": {"command": "ls"}},
        headers={"Authorization": f"Bearer {minted}"},
    )
    assert r.status_code == 200, r.text
