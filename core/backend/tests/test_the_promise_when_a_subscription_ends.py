# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""What the pricing page promises happens when someone stops paying.

The sentence under the plan, live on app.automatiabcn.com/pricing:

    "If a subscription ends, chat and the agent pause — and that is all. Your
     documents, meetings and keys stay on your server, readable, exportable and
     deletable, for as long as you want them there."

That is four falsifiable claims, and it is the reassurance that makes a
self-hosted subscription buyable at all: nobody puts a year of meetings behind
a $5 monthly charge if lapsing means losing them. So it is tested rather than
trusted.

  1. chat pauses
  2. reading still works
  3. export still works
  4. deletion still works

Claim 1 failing sells a subscription that does not need paying for. Claims 2-4
failing turn a lapsed subscription into a hostage situation — and would make a
sentence we publish false.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture()
def expired_trial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An install whose seven days ran out yesterday."""
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "mcp_require_license", True, raising=False)
    monkeypatch.setattr(settings, "license_key", "", raising=False)
    # The escape hatches are environment variables, not settings fields, and
    # ABS_TEST_MODE is on for the rest of the suite. Leaving either in place
    # would make every assertion below vacuous — the gate would allow the call
    # for a reason that has nothing to do with the subscription.
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)

    (tmp_path / "trial.json").write_text(
        json.dumps({"started_at": time.time() - 8 * 86400, "seen_at": time.time()}),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def fresh_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A server that has just been started for the first time.

    No trial.json, no licence key, no data — the state a customer is in ninety
    seconds after running install.sh.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "mcp_require_license", True, raising=False)
    monkeypatch.setattr(settings, "license_key", "", raising=False)
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    return tmp_path


def test_a_new_install_gets_its_seven_days_without_a_key(fresh_install):
    """The other half of the sentence, and the one every customer meets first.

    Every surface now says "seven days free, no card, no licence key" — the
    pricing page, the download page, the README in three languages, the
    installer's own closing line and the licence-delivery email. If a fresh
    install refused to work, all of them would be lying at once, and the
    customer would meet it before anything else in the product.
    """
    from app.licensing import gate as licence_gate
    from app.licensing import trial

    status = trial.status()
    assert status.active is True, "a brand-new install has no trial"
    assert status.days_left == 7, f"a new install got {status.days_left} days, not 7"

    decision = licence_gate.enforce()
    assert decision.allowed is True, (
        "a fresh install is refused service, while every page we publish says "
        "the first seven days need no card and no licence key"
    )


def test_the_trial_survives_a_restart(fresh_install):
    """Asking twice must not restart the clock.

    `status()` writes the file it just created, so a server that is restarted —
    or a container that is rebuilt, which is what `docker compose pull` does —
    must not hand out a second week. This is the cheap version of that: the
    start time has to be the same on the second read.
    """
    from app.licensing import trial

    first = trial.status().started_at
    second = trial.status().started_at
    assert first == second, "the trial clock restarted on the next request"


def test_the_trial_really_is_over(expired_trial):
    """The fixture has to produce the state the rest of the file assumes.

    A test that silently ran against an *active* trial would pass claims 2-4 for
    the wrong reason and prove nothing about claim 1.
    """
    from app.licensing import gate as licence_gate
    from app.licensing import trial

    assert trial.status().active is False
    assert licence_gate.evaluate().verdict is licence_gate.Verdict.TRIAL_EXPIRED


def test_chat_pauses(expired_trial):
    """Claim 1."""
    from app.licensing import gate as licence_gate

    decision = licence_gate.enforce()
    assert decision.allowed is False, "chat still runs after the trial ended"


def test_the_refusal_says_the_data_is_still_theirs(expired_trial):
    """A block that reads as data loss costs more than the subscription.

    The customer meets this message at the worst possible moment. It has to
    repeat the promise, not just deny the request.
    """
    from app.mcp.gate import _BLOCK_MESSAGE

    lowered = _BLOCK_MESSAGE.lower()
    for word in ("read", "export", "delet"):
        assert word in lowered, f"the refusal does not mention {word!r}"


@pytest.mark.parametrize(
    "module,claim",
    [
        ("app.api.meetings", "reading meetings"),
        ("app.api.me_data_export", "exporting everything"),
        ("app.api.me_account", "deleting the account"),
    ],
)
def test_the_data_paths_are_not_behind_the_licence_gate(expired_trial, module, claim):
    """Claims 2-4, checked at the source rather than the symptom.

    These modules must not import the licence gate at all. Checking a response
    code would only prove the one endpoint I happened to call; checking the
    import proves no endpoint in the module can be gated, including the ones
    added next month.
    """
    import importlib
    import inspect

    mod = importlib.import_module(module)
    source = inspect.getsource(mod)
    for forbidden in ("licensing import gate", "licence_gate", "license_gate"):
        assert forbidden not in source, (
            f"{claim} is behind the licence gate — a lapsed subscription would "
            f"hold the customer's own data hostage, and the pricing page says "
            f"otherwise"
        )


def test_only_chat_is_gated(expired_trial):
    """The promise is "chat and the agent pause — and that is all".

    "And that is all" is the part that can rot: someone adds a gate to a new
    endpoint for a good local reason, and the sentence on the pricing page
    quietly becomes false. This counts the modules that enforce it.
    """
    import pathlib

    api = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    enforcing = sorted(
        p.name
        for p in api.rglob("*.py")
        if "licence_gate.enforce(" in p.read_text(encoding="utf-8", errors="ignore")
    )
    assert enforcing == ["chat.py"], (
        "something other than chat now refuses service without a subscription: "
        f"{enforcing}. Either that is wrong, or the pricing page needs to stop "
        f"saying 'and that is all'."
    )
