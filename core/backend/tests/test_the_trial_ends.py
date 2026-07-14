# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The product is a monthly subscription with a seven-day trial.

Before this, a server with no licence key answered questions forever. That was
called "the free tier", and the pricing page — which sells four paid plans and no
free one — had never heard of it. A server that works indefinitely without a
subscription is not a trial; it is the product, given away.

What the end of a trial must NOT do is take the customer's things away. Their
documents, their transcripts, their provider keys: still there, still readable,
still exportable, still deletable. Chat and the agent stop. Nothing else does.

And the two surfaces have to agree. The chat gate and the MCP gate were separate
implementations of the same rule, and only one of them knew what a trial was — so
a customer on day three would have been served by their panel and refused by
their editor, or (worse, and this was the real case) served by their editor
forever while the panel told them their trial was over.
"""

from __future__ import annotations

import time

import pytest

from app.licensing import gate as licence_gate
from app.licensing import trial
from app.licensing.gate import Verdict


@pytest.fixture(autouse=True)
def _no_key_no_bypass(monkeypatch, tmp_path):
    """A server with no licence key, no test-mode bypass, and a data dir of its own."""
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "", raising=False)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    monkeypatch.setattr(licence_gate, "_demo_active", lambda: False)


def _install_happened(days_ago: float, tmp_path) -> None:
    started = time.time() - days_ago * 86400
    (tmp_path / "trial.json").write_text(
        f'{{"started_at": {started}, "seen_at": {started}}}', encoding="utf-8"
    )


def test_a_fresh_install_is_on_trial(tmp_path) -> None:
    decision = licence_gate.enforce()
    assert decision.allowed is True
    assert decision.verdict is Verdict.TRIAL
    assert trial.status().days_left == 7


def test_day_six_still_works(tmp_path) -> None:
    _install_happened(6, tmp_path)
    decision = licence_gate.enforce()
    assert decision.allowed is True
    assert decision.verdict is Verdict.TRIAL
    assert trial.status().days_left == 1


def test_day_eight_does_not(tmp_path) -> None:
    _install_happened(8, tmp_path)
    decision = licence_gate.enforce()
    assert decision.allowed is False
    assert decision.verdict is Verdict.TRIAL_EXPIRED


def test_what_the_customer_is_told_when_it_ends(tmp_path) -> None:
    """Not an enum. A sentence, and specifically the sentence that says their
    data is still theirs — which is the first thing a person wonders."""
    _install_happened(9, tmp_path)
    detail = licence_gate.enforce().detail

    assert "trial_expired" in detail  # the panel keys off this
    assert "seven-day trial is over" in detail
    assert "delete" in detail and "export" in detail
    assert "Settings" in detail


def test_winding_the_clock_back_does_not_buy_a_second_trial(tmp_path) -> None:
    """The obvious attack on any local trial, and the obvious defence.

    The file records the latest moment this server has ever seen. If `now` is
    behind it, the clock moved backwards, and the last thing we saw stands in for
    now. (A reinstall still resets it — this is the customer's machine and nothing
    running on it can prevent that. The licence agreement covers what the code
    cannot.)
    """
    started = time.time() - 8 * 86400
    seen = time.time()  # the server has seen today
    (tmp_path / "trial.json").write_text(
        f'{{"started_at": {started}, "seen_at": {seen}}}', encoding="utf-8"
    )

    # …and now the clock says it is five days ago.
    yesterday = time.time() - 5 * 86400
    state = trial.status_from(started, max(yesterday, seen))
    assert state.active is False, "moving the clock back handed out another trial"


def test_deleting_the_trial_file_is_not_a_fresh_trial(tmp_path, monkeypatch) -> None:
    """`rm trial.json` would otherwise be an unlimited supply of trials.

    When the file is gone but the install plainly is not new, the trial is dated
    from the oldest evidence on the box — here, the wizard's own state file.
    """
    long_ago = time.time() - 30 * 86400
    monkeypatch.setattr(trial, "_oldest_evidence", lambda: long_ago)

    state = trial.status()
    assert state.active is False, "deleting one file restarted the trial"
    assert (tmp_path / "trial.json").is_file(), "the rebuilt state was not written back"


def test_a_licensed_server_is_not_on_trial(tmp_path, monkeypatch) -> None:
    """The trial is only for servers without a key: a paying customer whose
    machine has been up for a year is not eight days into anything."""
    from app.config import settings
    from app.licensing import verifier

    _install_happened(400, tmp_path)
    monkeypatch.setattr(settings, "license_key", "a-real-key", raising=False)
    monkeypatch.setattr(
        verifier, "verify_license", lambda token: {"jti": "j1", "seat_count": 5}
    )
    monkeypatch.setattr(licence_gate, "_revoked", lambda payload: None)

    decision = licence_gate.enforce()
    assert decision.allowed is True
    assert decision.verdict is Verdict.LICENSED


def test_the_fourteen_day_demo_is_not_a_second_free_week(tmp_path) -> None:
    """There was a second clock, and it ran twice as long.

    `licensing.demo` used to own a fourteen-day window armed by the same empty
    licence key, and the gate honoured it *before* the trial — so the seven-day
    trial the founder priced could be sat out for a fortnight, and the panel and
    the editor would each have believed a different number. There is one window
    now, and `demo` reads it.
    """
    from app.licensing import demo

    assert demo.DEMO_DURATION_DAYS == trial.TRIAL_DAYS == 7

    _install_happened(10, tmp_path)  # past the trial, inside the old demo
    assert demo.is_active() is False
    assert demo.status()["days_remaining"] == 0
    assert licence_gate.enforce().allowed is False, (
        "the retired fourteen-day demo was still handing out a second free week"
    )


def test_an_install_that_was_demoing_keeps_its_start_date(tmp_path) -> None:
    """The rename must not be a gift.

    An install already ten days into the old demo has no `trial.json`. If the
    trial dated itself from the upgrade, every existing install would have woken
    up with a brand new week.
    """
    import json

    started = time.time() - 10 * 86400
    (tmp_path / "demo_state.json").write_text(
        json.dumps({"started_at": started, "expires_at": started + 14 * 86400}),
        encoding="utf-8",
    )

    assert trial.status().active is False
    assert licence_gate.enforce().verdict is Verdict.TRIAL_EXPIRED


def test_the_editor_and_the_panel_agree(tmp_path) -> None:
    """The MCP gate had its own copy of the licence rule and did not know what a
    trial was. Whatever the chat path decides, the tools decide."""
    from app.mcp import gate as mcp_gate

    _install_happened(2, tmp_path)
    assert mcp_gate._gate_status()["allowed"] is True
    assert mcp_gate._gate_status()["trial_active"] is True

    _install_happened(20, tmp_path)
    status = mcp_gate._gate_status()
    assert status["allowed"] is False, (
        "the trial was over and the customer's editor kept working — the tools are "
        "the product, and the product is a subscription"
    )
    assert "trial" in status["detail"]
