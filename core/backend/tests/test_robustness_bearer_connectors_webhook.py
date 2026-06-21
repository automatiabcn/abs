"""Robustness regression suite (repo audit round).

Covers three independently-found edge cases that previously raised an
unhandled 500 instead of a clean, expected response:

1. Admin bearer gates (smart_link, status_page) when the header is exactly
   ``"bearer "`` with no token — ``split(None, 1)[1]`` used to IndexError.
2. Stripe webhook with a valid signature but no ``type`` field.
3. Connector sync when the stored credential blob decrypts to empty/garbage.
"""

from __future__ import annotations

import pytest
import stripe

from app.api import smart_link as smart_link_mod
from app.api import status_page as status_page_mod
from fastapi import HTTPException


# --- 1. empty-bearer admin gates -------------------------------------------

def test_smart_link_check_admin_empty_bearer_is_401_not_500():
    with pytest.raises(HTTPException) as exc:
        smart_link_mod._check_admin("bearer ")  # trailing space, no token
    assert exc.value.status_code == 401


def test_smart_link_check_admin_bearer_only_is_401_not_500():
    with pytest.raises(HTTPException) as exc:
        smart_link_mod._check_admin("bearer")  # no space at all is rejected earlier
    assert exc.value.status_code == 401


def test_status_page_require_admin_empty_bearer_is_401_not_500():
    with pytest.raises(HTTPException) as exc:
        status_page_mod._require_admin("bearer    ")  # only whitespace token
    assert exc.value.status_code == 401


# --- 2. stripe webhook missing type ----------------------------------------

def test_webhook_valid_signature_missing_type_is_400(client, monkeypatch):
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda *a, **k: {"id": "evt_no_type", "data": {"object": {}}},
    )
    r = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert r.status_code == 400, r.text


# --- 3. connector sync with unreadable credentials --------------------------

async def test_connector_sync_unreadable_credentials_is_graceful(monkeypatch):
    from app.connectors import service as svc

    # A connector row exists with a non-empty blob, but decrypt yields "".
    class _Row:
        encrypted_credentials = "ciphertext-that-decrypts-to-nothing"

    monkeypatch.setattr(svc, "_get_row", lambda db, t, c: _Row())
    monkeypatch.setattr(svc, "decrypt_secret_value", lambda blob: "")

    # csv_import has a real adapter; sync must not raise JSONDecodeError.
    out = await svc.sync(tenant_slug="tAudit", connector_id="csv_import")
    assert out["ok"] is False
    assert out["error"] == "credentials_unreadable"
