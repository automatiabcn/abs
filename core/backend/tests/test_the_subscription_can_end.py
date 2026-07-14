# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A monthly subscription that cannot end is not a subscription.

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

import time
from datetime import datetime, timedelta, timezone
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


class _FakeSub(dict):
    pass


def test_the_seller_refuses_a_cancelled_subscription(signing, monkeypatch) -> None:
    """The whole mechanism, from the other end: no live subscription, no key.

    And the refusal says what happens to their data, because that is the first
    thing a person wonders when software tells them it is stopping.
    """
    from fastapi import HTTPException

    from app.api import license_renew
    from app.db.models import License
    from app.db.session import get_engine
    from sqlmodel import Session

    monkeypatch.setattr(signing, "stripe_secret_key", "sk_test", raising=False)
    token = _key(customer="cus_gone", days=1)

    from app.licensing.verifier import verify_license

    jti = verify_license(token)["jti"]
    with Session(get_engine()) as db:
        db.add(
            License(
                jti=jti,
                customer_email="a@example.com",
                customer_id_stripe="cus_gone",
                tier="team",
                seat_count=3,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        db.commit()

    monkeypatch.setattr(license_renew, "_subscription_for", lambda cid: None)

    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            license_renew.renew_license(
                license_renew.RenewRequest(license_key=token), None
            )
        )

    assert exc.value.status_code == 402
    assert "exported" in exc.value.detail and "deleted" in exc.value.detail


def test_a_live_subscription_gets_the_seats_it_pays_for(signing, monkeypatch) -> None:
    """Seats come off the subscription, not off the old key.

    An admin who added two seats last week is paying for them now. If the renewed
    key still said "3", the seat gate would refuse the people they had just bought
    room for — and it would be us, not them, who had made the mistake.
    """
    from sqlmodel import Session

    from app.api import license_renew
    from app.db.models import License
    from app.db.session import get_engine
    from app.licensing.verifier import verify_license

    monkeypatch.setattr(signing, "stripe_secret_key", "sk_test", raising=False)
    token = _key(customer="cus_live", days=1, seats=3)
    jti = verify_license(token)["jti"]
    with Session(get_engine()) as db:
        db.add(
            License(
                jti=jti,
                customer_email="b@example.com",
                customer_id_stripe="cus_live",
                tier="team",
                seat_count=3,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        db.commit()

    period_end = time.time() + 30 * 86400
    monkeypatch.setattr(
        license_renew,
        "_subscription_for",
        lambda cid: {
            "status": "active",
            "current_period_end": period_end,
            "items": {"data": [{"quantity": 5}]},
        },
    )

    import asyncio

    out = asyncio.run(
        license_renew.renew_license(license_renew.RenewRequest(license_key=token), None)
    )

    payload = verify_license(out["license_key"])
    assert payload["seat_count"] == 5
    assert out["seat_count"] == 5
    # One period, plus the grace window — not a year.
    assert 30 <= (payload["exp"] - time.time()) / 86400 <= 40, (
        "a monthly subscriber was handed a key that outlives their subscription"
    )


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
