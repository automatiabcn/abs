# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The settings page and the chat gate must not disagree about the licence.

They used to. `/v1/license/info` classified the licence itself — reading
`License.revoked_at` from the database — while the chat gate watched the
activation cache. Neither knew about the other, and neither had a grace window.
So a licence revoked by a refund read "licensed" on the settings page while chat
answered 403, and an expired-but-in-grace licence read "expired" on a server
that was working perfectly well.

Both now come from one function, `licence_gate.evaluate()`. These tests hold the
two surfaces against each other so they cannot drift apart again.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.licensing import gate as licence_gate
from app.licensing import phone_home
from app.licensing.generator import generate_license
from app.licensing.keys import generate_keypair


@pytest.fixture
def licensed_app(tmp_path: Path, monkeypatch, client: TestClient):
    """`client` is requested first on purpose: building it runs the app's
    lifespan, and the lifespan only skips the MCP session manager while
    ABS_TEST_MODE is set. Unset the flag before the app boots and the manager
    starts for real — then refuses to start a second time, and every test after
    the first errors out in setup rather than failing honestly."""
    from app.config import settings

    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    monkeypatch.setattr("app.licensing.demo.is_active", lambda: False)

    private_pem = tmp_path / "private.pem"
    public_pem = tmp_path / "public.pem"
    generate_keypair(str(private_pem), str(public_pem))
    monkeypatch.setattr(settings, "private_key_path", str(private_pem))
    monkeypatch.setattr(settings, "public_key_path", str(public_pem))
    monkeypatch.setattr(phone_home, "STATE_PATH", tmp_path / "license_activation.json")

    yield tmp_path / "license_activation.json"

    os.environ["ABS_TEST_MODE"] = "1"


def _license(monkeypatch, **kwargs) -> str:
    from app.config import settings

    token = generate_license("cust_panel", **kwargs)
    monkeypatch.setattr(settings, "license_key", token)
    return token


def _chat_allowed() -> bool:
    try:
        chat_api._assert_license_ok()
        return True
    except HTTPException:
        return False


def _info(client: TestClient) -> dict:
    res = client.get("/v1/license/info")
    assert res.status_code == 200, res.text
    return res.json()


def test_a_working_licence_reads_as_working(licensed_app, monkeypatch, client):
    _license(monkeypatch)

    info = _info(client)

    assert info["status"] == "licensed"
    assert info["allowed"] is True
    assert _chat_allowed()


def test_a_licence_in_grace_says_so_instead_of_saying_expired(
    licensed_app, monkeypatch, client
):
    """The server is answering. The page used to call this "expired", which is
    the kind of report that makes an operator restart things at midnight."""
    _license(monkeypatch, valid_days=-1)

    info = _info(client)

    assert info["status"] == "in_grace"
    assert info["allowed"] is True
    assert info["grace_days"] == licence_gate.GRACE_DAYS
    assert _chat_allowed(), "the page said it works — it had better work"


def test_a_revoked_licence_reads_as_revoked_on_both_surfaces(
    licensed_app, monkeypatch, client
):
    """The refund case. The page has always known; the gate did not."""
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
                customer_id="cust_panel",
                tier="self-host",
                seat_count=1,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                revoked_at=datetime.now(timezone.utc),
                revoked_reason="refunded",
            )
        )
        db.commit()

    info = _info(client)

    assert info["status"] == "revoked"
    assert info["allowed"] is False
    assert not _chat_allowed(), "the page said refused — chat must refuse too"


def test_an_expired_licence_past_grace_reads_as_expired_and_refuses(
    licensed_app, monkeypatch, client
):
    _license(monkeypatch, valid_days=-(licence_gate.GRACE_DAYS + 3))

    info = _info(client)

    assert info["status"] == "expired"
    assert info["allowed"] is False
    assert not _chat_allowed()


def test_an_install_with_no_key_is_reported_as_on_trial_and_still_works(
    licensed_app, monkeypatch, client
):
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "")

    info = _info(client)

    assert info["status"] == "trial"
    assert info["allowed"] is True
    assert _chat_allowed()


def test_a_finished_trial_is_not_described_as_licensed(
    licensed_app, monkeypatch, client, tmp_path
):
    """The failure this whole file exists to prevent, in its newest form.

    When the trial verdicts were added to the gate but not to `/v1/license/info`,
    they fell through to the licensed branch: the settings page told the owner of
    an expired-trial server that it was "licensed" — with every licence field
    null — while chat refused every message. The page and the gate have to break
    the same way.
    """
    import json
    import time

    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "")
    # Into *this install's* data dir. Pointing `data_dir` at an empty directory
    # instead makes the app think it was never set up, and every request comes
    # back as the setup wizard.
    started = time.time() - 30 * 86400
    (Path(settings.data_dir) / "trial.json").write_text(
        json.dumps({"started_at": started, "seen_at": started}), encoding="utf-8"
    )

    info = _info(client)

    assert info["status"] == "trial_expired"
    assert info["allowed"] is False
    assert not _chat_allowed()
    assert "export" in info["detail"], (
        "the page refuses without telling the customer their data is still theirs"
    )


def test_a_server_revocation_reaches_the_settings_page_too(
    licensed_app, monkeypatch, client
):
    """Revocation can arrive from the activation server rather than the DB."""
    _license(monkeypatch)
    last = datetime.now(timezone.utc).isoformat()
    licensed_app.write_text(
        json.dumps({"valid": False, "reason": "chargeback", "last_check": last})
    )

    info = _info(client)

    assert info["status"] == "revoked"
    assert info["allowed"] is False
    assert info["reason"] == "chargeback"
    assert not _chat_allowed()
