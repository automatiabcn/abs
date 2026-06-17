# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (b) — multiple MCP tokens.

Tokens stay HMAC-stateless, but an issuance ledger now lets the panel LIST every
issued token and revoke a listed one by digest (the raw token is shown only once
at mint, so the UI cannot revoke by the raw string).
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


def _mint(client, label: str) -> dict:
    r = client.post(
        "/v1/mcp/tokens",
        json={"label": label, "scope": "all", "ttl_days": 30},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_multiple_tokens_listed_and_revoked_by_digest(admin_client):
    a = _mint(admin_client, "ci-bot")
    b = _mint(admin_client, "dev-laptop")
    assert a["token"] != b["token"]  # each mint is a distinct token

    rows = admin_client.get("/v1/mcp/tokens").json()
    by_label = {t["label"]: t for t in rows}
    assert "ci-bot" in by_label and "dev-laptop" in by_label
    assert by_label["ci-bot"]["status"] == "active"
    assert by_label["dev-laptop"]["status"] == "active"

    # revoke ONE by digest — the panel never re-sees the raw token
    rv = admin_client.post(
        "/v1/mcp/tokens/revoke",
        json={"token_digest": by_label["dev-laptop"]["token_digest"]},
    )
    assert rv.status_code == 204, rv.text

    after = {t["label"]: t["status"]
             for t in admin_client.get("/v1/mcp/tokens").json()}
    assert after["dev-laptop"] == "revoked"
    assert after["ci-bot"] == "active"      # the other token is untouched


def test_revoke_unknown_digest_is_404(admin_client):
    r = admin_client.post(
        "/v1/mcp/tokens/revoke", json={"token_digest": "0" * 64}
    )
    assert r.status_code == 404


def test_revoke_requires_token_or_digest(admin_client):
    r = admin_client.post("/v1/mcp/tokens/revoke", json={"reason": "x"})
    assert r.status_code in (400, 422)
