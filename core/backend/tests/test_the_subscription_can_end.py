# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A monthly subscription that cannot end is not a subscription.

(The seller's half — minting the next key, and asking Stripe whether the
subscription is still alive — lives in the Cloudflare Worker that already owns
revocation, and is tested there: `infra/cf-worker/licensing.test.mjs`. What is
tested here is the customer's half: when this server asks, what it will accept,
and what it does when nobody answers.)

The licence is a signed token, checked offline, on a machine we cannot see. That
is the product's best property and the thing that makes monthly billing hard: a
key minted to last a year does not care that the customer cancelled in month two.
Enforcement would rest entirely on a revocation call that an air-gapped server
never receives — which is to say, on nothing.

So the key lasts one billing period plus the grace window, and the customer's
server asks for the next one shortly before it runs out. Stop paying, and the key
runs out where it sits. Nobody has to switch anything off.

What must never happen — the failure these tests exist for — is the *reverse*: a
customer who is paying, and whose server stops because our renewal service was
unreachable. Renewal runs on a timer, never in a request path, and every failure
mode of it ends in "nothing was refused".
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.licensing import renewal
from app.licensing.generator import generate_license
from app.licensing.keys import generate_keypair


@pytest.fixture()
def signing(tmp_path: Path, monkeypatch):
    """A real keypair, and no licence installed yet."""
    from app.config import settings

    priv, pub = tmp_path / "priv.pem", tmp_path / "pub.pem"
    generate_keypair(str(priv), str(pub))
    monkeypatch.setattr(settings, "private_key_path", str(priv))
    monkeypatch.setattr(settings, "public_key_path", str(pub))
    monkeypatch.setattr(settings, "license_key", "", raising=False)
    monkeypatch.setattr(
        settings, "license_renewal_url", "https://billing.test/v1/license/renew"
    )
    # The .env write is not what these tests are about.
    monkeypatch.setattr("app.api.setup._persist_encrypted_secret", lambda *a, **k: True)
    return settings


def _key(customer: str = "cus_1", days: int = 30, seats: int = 1) -> str:
    return generate_license(
        customer_id=customer, tier="team", seat_count=seats, valid_days=days
    )


def test_a_month_old_key_is_due_and_a_fresh_one_is_not(signing) -> None:
    assert renewal.is_due(_key(days=30)) is False
    assert renewal.is_due(_key(days=2)) is True, (
        "a key with two days left was never asked to renew — it would have "
        "expired under a paying customer"
    )


def test_the_renewed_key_is_installed(signing, monkeypatch) -> None:
    signing.license_key = _key(days=2)
    fresh = _key(days=31)

    async def _post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"license_key": fresh})

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)

    import asyncio

    assert asyncio.run(renewal.renew_if_due()) is True
    assert signing.license_key == fresh


def test_our_outage_never_stops_a_paying_customer(signing, monkeypatch) -> None:
    """The failure that would matter most, and the one nobody would forgive."""
    original = _key(days=2)
    signing.license_key = original

    async def _boom(self, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("billing.test is down")

    monkeypatch.setattr(httpx.AsyncClient, "post", _boom)

    import asyncio

    assert asyncio.run(renewal.renew_if_due()) is False
    assert signing.license_key == original, "an outage of ours took their key away"


def test_a_key_for_someone_else_is_not_a_renewal(signing) -> None:
    """A renewal endpoint that can hand this server a different customer's licence
    is not a renewal endpoint, it is a licence swap."""
    signing.license_key = _key(customer="cus_me", days=2)
    theirs = _key(customer="cus_them", days=400)

    assert renewal.apply_renewed_key(theirs) is False
    assert "cus_them" not in signing.license_key


def test_an_older_key_cannot_replace_a_newer_one(signing) -> None:
    """Otherwise a replayed response is a downgrade someone else gets to choose."""
    current = _key(days=300)
    signing.license_key = current

    assert renewal.apply_renewed_key(_key(days=5)) is False
    assert signing.license_key == current


def test_an_unsigned_key_is_never_installed(signing) -> None:
    assert renewal.apply_renewed_key("not.a.jwt") is False
    assert renewal.apply_renewed_key("") is False


def test_a_trial_has_nothing_to_renew(signing) -> None:
    import asyncio

    signing.license_key = ""
    assert asyncio.run(renewal.renew_if_due()) is False


def test_a_failing_renewal_is_not_a_silent_one(signing, monkeypatch) -> None:
    """The failure that would cost us a paying customer without anyone noticing.

    A renewal that quietly fails looks exactly like one that quietly works — until
    the morning the key runs out and the server stops for a reason nobody was
    warned about. Every attempt is recorded, and the licence page reports it while
    there are still days left to act.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    signing.license_key = _key(days=2)

    async def _boom(self, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("nothing is listening")

    monkeypatch.setattr(httpx.AsyncClient, "post", _boom)

    import asyncio

    asyncio.run(renewal.renew_if_due())

    last = renewal.last_attempt()
    assert last["ok"] is False
    assert "could not reach" in last["error"]

    with TestClient(app) as client:
        info = client.get("/v1/license/info").json()

    assert info["renewal"]["last_attempt_ok"] is False
    assert info["renewal"]["days_left"] <= 2
    assert info["renewal"]["last_error"]
