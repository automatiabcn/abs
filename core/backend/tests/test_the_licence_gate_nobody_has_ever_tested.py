# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The licence gate — the product's front door, and the one thing 2900 tests
never touched.

`conftest` sets `ABS_TEST_MODE=1` session-wide and the gate's first act is to
return when it sees that, so every other test in this repository exercises an
*unlicensed* application. These tests delete the flag and drive the real thing.

What they pin is the rule the gate now follows:

    a bad signature refuses          — the licence is wrong
    a server revocation refuses      — the licence was cancelled
    a network failure never refuses  — that is our problem, not the customer's
    no licence key at all is allowed — that is the free tier

The old gate did none of this. It read a cached activation state, and when the
cache was missing or older than thirty seconds it blocked the request on a
*synchronous* call to our activation server. A fresh install therefore answered
403 to its own first chat message, because it had not phoned home yet — the
product was dead in its first minute, on the customer's machine, for a reason
that had nothing to do with the customer. And "we could not reach the licence
server" produced exactly the same refusal as "this licence is revoked", so any
outage of ours locked out everyone who had paid us.

Signatures are checked offline, against a public key on the customer's own disk.
Revocation is the only thing the network is for, and the only thing it can
refuse on — which is safe, because the cache is written from server responses
alone (`phone_home._persist_activation_state`); an offline-grace verdict is
never persisted. So a cached `valid: false` means the server said no. A missing
cache means we never got to ask.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import chat as chat_api
from app.licensing import gate as licence_gate
from app.licensing import phone_home
from app.licensing.generator import generate_license
from app.licensing.keys import generate_keypair


@pytest.fixture
def licensed_app(tmp_path: Path, monkeypatch):
    """The application as a customer runs it: no test-mode escape hatch, a real
    signing keypair, and an activation cache that starts out empty — which is
    what a fresh install has."""
    from app.config import settings

    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    # Demo mode is a separate door, and an empty licence key auto-opens it.
    # Pin it shut so the licence path is what actually runs.
    monkeypatch.setattr("app.licensing.demo.is_active", lambda: False)

    private_pem = tmp_path / "private.pem"
    public_pem = tmp_path / "public.pem"
    generate_keypair(str(private_pem), str(public_pem))
    monkeypatch.setattr(settings, "private_key_path", str(private_pem))
    monkeypatch.setattr(settings, "public_key_path", str(public_pem))

    state_path = tmp_path / "license_activation.json"
    monkeypatch.setattr(phone_home, "STATE_PATH", state_path)

    yield state_path

    os.environ["ABS_TEST_MODE"] = "1"


def _license(monkeypatch, **kwargs) -> str:
    from app.config import settings

    token = generate_license("cust_gate", **kwargs)
    monkeypatch.setattr(settings, "license_key", token)
    return token


def _server_said(state_path: Path, *, valid: bool, reason: str, age_secs: float = 5.0):
    """Write the activation cache exactly as a server response would."""
    last = datetime.now(timezone.utc) - timedelta(seconds=age_secs)
    state_path.write_text(
        json.dumps({"valid": valid, "reason": reason, "last_check": last.isoformat()})
    )


# ---------------------------------------------------------------------------
# The case that killed the product: a fresh install, and us unreachable.
# ---------------------------------------------------------------------------


def test_a_valid_licence_works_before_we_have_ever_been_phoned(
    licensed_app, monkeypatch
):
    """No activation cache at all — the install has not reached us yet, or
    cannot. The signature is right there on disk and says everything we need.

    This is the test that would have caught the 403-in-the-first-minute."""
    _license(monkeypatch)
    assert not licensed_app.exists(), "precondition: never activated"

    decision = licence_gate.evaluate()

    assert decision.allowed
    assert decision.verdict is licence_gate.Verdict.LICENSED
    chat_api._assert_license_ok()  # does not raise


def test_the_gate_never_opens_a_socket(licensed_app, monkeypatch):
    """The old gate called our activation server from inside
    `POST /v1/chat/completions`, behind a 3-second timeout. Our host sat in the
    request path of every chat turn on every customer's machine."""
    import httpx

    def _explode(*args, **kwargs):
        raise AssertionError("the licence gate made a network call")

    monkeypatch.setattr(httpx, "Client", _explode)
    monkeypatch.setattr(httpx, "AsyncClient", _explode)
    _license(monkeypatch)

    chat_api._assert_license_ok()  # does not raise, and does not dial


# ---------------------------------------------------------------------------
# The signature is the gate.
# ---------------------------------------------------------------------------


def test_a_forged_licence_is_refused(licensed_app, monkeypatch):
    """Signed with a key that is not ours."""
    from app.config import settings

    other_private = licensed_app.parent / "attacker.pem"
    other_public = licensed_app.parent / "attacker.pub"
    generate_keypair(str(other_private), str(other_public))

    monkeypatch.setattr(settings, "private_key_path", str(other_private))
    forged = generate_license("cust_forged")
    monkeypatch.setattr(settings, "license_key", forged)
    # ...but the install still verifies against *our* public key.

    decision = licence_gate.evaluate()

    assert not decision.allowed
    assert decision.verdict is licence_gate.Verdict.INVALID
    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()
    assert exc.value.status_code == 403


def test_a_garbage_licence_key_is_refused(licensed_app, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "not-a-jwt-at-all")

    assert licence_gate.evaluate().verdict is licence_gate.Verdict.INVALID


# ---------------------------------------------------------------------------
# Expiry, and the week of grace after it.
# ---------------------------------------------------------------------------


def test_a_licence_that_expired_yesterday_still_works(licensed_app, monkeypatch):
    """Renewals land late and invoices sit in inboxes. A customer mid-sentence
    in a chat window is not the person to punish for it."""
    _license(monkeypatch, valid_days=-1)

    decision = licence_gate.evaluate()

    assert decision.allowed
    assert decision.verdict is licence_gate.Verdict.IN_GRACE
    chat_api._assert_license_ok()  # does not raise


def test_a_licence_expired_past_the_grace_window_is_refused(licensed_app, monkeypatch):
    _license(monkeypatch, valid_days=-(licence_gate.GRACE_DAYS + 2))

    decision = licence_gate.evaluate()

    assert not decision.allowed
    assert decision.verdict is licence_gate.Verdict.EXPIRED
    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()
    # The panel keys off the prefix; the rest of the sentence is for the person
    # reading it, and it has one job — say that their data is still theirs.
    assert exc.value.detail.startswith("license_expired")
    assert "export" in exc.value.detail and "delete" in exc.value.detail


def test_the_grace_window_is_seven_days(licensed_app, monkeypatch):
    """Written down, so it is a decision rather than a constant nobody read."""
    assert licence_gate.GRACE_DAYS == 7

    _license(monkeypatch, valid_days=-(licence_gate.GRACE_DAYS - 1))
    assert licence_gate.evaluate().allowed

    _license(monkeypatch, valid_days=-(licence_gate.GRACE_DAYS + 1))
    assert not licence_gate.evaluate().allowed


# ---------------------------------------------------------------------------
# Revocation — the one thing the network is for.
# ---------------------------------------------------------------------------


def test_a_revoked_licence_is_refused_and_says_why(licensed_app, monkeypatch):
    """A refund, a chargeback, a cancelled contract. The signature is still
    perfectly valid — only the server knows this licence is dead."""
    _license(monkeypatch)
    _server_said(licensed_app, valid=False, reason="refunded")

    decision = licence_gate.evaluate()

    assert not decision.allowed
    assert decision.verdict is licence_gate.Verdict.REVOKED
    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()
    assert exc.value.detail == "license_revoked:refunded"


def test_a_licence_revoked_in_the_database_is_refused(licensed_app, monkeypatch):
    """There are two revocation sources and the chat gate watched the wrong one.

    A refund sets `License.revoked_at` in the database — that is the flow the
    admin console drives, and the one `/v1/license/info` has always reported.
    The chat gate only ever looked at the activation cache, so a licence
    revoked here kept answering chat requests as if nothing had happened.
    """
    import jwt as pyjwt
    from sqlmodel import Session

    from app.db.models import License
    from app.db.session import get_engine

    token = _license(monkeypatch)
    claims = pyjwt.decode(token, options={"verify_signature": False})

    with Session(get_engine()) as db:
        db.add(
            License(
                jti=claims["jti"],
                customer_id="cust_gate",
                tier="self-host",
                seat_count=1,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                revoked_at=datetime.now(timezone.utc),
                revoked_reason="refunded",
            )
        )
        db.commit()

    decision = licence_gate.evaluate()

    assert not decision.allowed
    assert decision.verdict is licence_gate.Verdict.REVOKED
    assert decision.detail == "license_revoked:refunded"


def test_a_revocation_bites_even_inside_the_grace_window(licensed_app, monkeypatch):
    """Grace forgives a late payment. It does not forgive a refund."""
    _license(monkeypatch, valid_days=-1)
    _server_said(licensed_app, valid=False, reason="chargeback")

    assert licence_gate.evaluate().verdict is licence_gate.Verdict.REVOKED


def test_a_stale_revocation_still_refuses(licensed_app, monkeypatch):
    """The old gate treated a cache older than thirty seconds as worthless and
    went to the network. A revocation does not expire while we are offline —
    if anything, it is the fact we most want to keep."""
    _license(monkeypatch)
    _server_said(licensed_app, valid=False, reason="revoked", age_secs=90 * 86400)

    assert licence_gate.evaluate().verdict is licence_gate.Verdict.REVOKED


def test_an_offline_marker_in_the_cache_never_refuses(licensed_app, monkeypatch):
    """`never_activated` and `offline_grace*` are written by *us*, locally, when
    the server could not be reached. They are not verdicts. They cannot reach
    the cache today — `phone_home` does not persist them — but if a future edit
    starts persisting them, the failure mode is every customer locked out of a
    product they paid for, so the gate refuses to read them as refusals."""
    _license(monkeypatch)

    for reason in ("never_activated", "offline_grace (3.0d)", "offline_grace_expired"):
        _server_said(licensed_app, valid=False, reason=reason)
        decision = licence_gate.evaluate()
        assert decision.allowed, f"{reason!r} was treated as a revocation"


# ---------------------------------------------------------------------------
# The free tier.
# ---------------------------------------------------------------------------


def test_an_install_with_no_licence_key_is_on_trial_and_can_chat(
    licensed_app, monkeypatch
):
    """A fresh install with no key works, immediately and completely.

    This used to be the free tier — no key, no limit, forever. The product is a
    monthly subscription now, so the same install is a trial: it still answers on
    day one without anyone typing a licence, and it stops after seven days. What
    it must never do is answer 403 to its own first message.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "")

    decision = licence_gate.evaluate()

    assert decision.allowed
    assert decision.verdict is licence_gate.Verdict.TRIAL
    chat_api._assert_license_ok()  # does not raise


def test_a_trial_that_has_run_out_stops_chat(licensed_app, monkeypatch, tmp_path):
    """And says so in a sentence, not an enum — including the part a person
    actually wants to know, which is what happens to their documents."""
    import json
    import time

    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    started = time.time() - 30 * 86400
    (tmp_path / "trial.json").write_text(
        json.dumps({"started_at": started, "seen_at": started}), encoding="utf-8"
    )

    decision = licence_gate.evaluate()

    assert not decision.allowed
    assert decision.verdict is licence_gate.Verdict.TRIAL_EXPIRED
    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()
    assert exc.value.detail.startswith("trial_expired")
    assert "export" in exc.value.detail


# ---------------------------------------------------------------------------
# The flag that hid all of the above.
# ---------------------------------------------------------------------------


def test_the_test_mode_flag_is_the_only_thing_holding_the_door_open(monkeypatch):
    """Named plainly, because it is the reason none of this was known. Every one
    of the ~2900 tests in this suite runs with ABS_TEST_MODE=1, and the gate's
    first line returns on it. The suite tests an application with no licensing
    in it at all."""
    from app.config import settings

    monkeypatch.setenv("ABS_TEST_MODE", "1")
    monkeypatch.setattr(settings, "license_key", "not-a-jwt-at-all")

    assert licence_gate.enforce().allowed  # a garbage key, and still allowed

    # But only the *enforcement* is bypassed. `evaluate()` still says what is
    # actually true, because the settings page reads it, and a page that
    # inherits the gate's escape hatch would report a garbage key as
    # "licensed" on any dev box — which is how it behaved for about an hour
    # while this was being written.
    assert licence_gate.evaluate().verdict is licence_gate.Verdict.INVALID
