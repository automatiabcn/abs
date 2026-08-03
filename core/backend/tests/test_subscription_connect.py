# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Connecting a subscription, and the three ways that page can lie.

Most people arriving at ABS have ChatGPT Plus or Claude Pro and no API key.
A subscription is not API credit, so there is nothing to paste — the path is
install a CLI, sign in once, and let ABS call it.

Three lies are possible on that screen, and each is worse than showing nothing:

* **"ready" for an installed CLI nobody has signed into.** The same defect as a
  mistyped key stored with a green tick (07-31): the product says go and the
  first real call fails.
* **"signed out" for a CLI that timed out.** Sends the customer to
  re-authenticate something that was already authenticated, and the loop has
  no exit.
* **"not installed" for a CLI that is installed somewhere unusual.** nvm and
  ~/.local/bin are not on the PATH of a service started by systemd.
"""

from __future__ import annotations

import os

import app.mcp.server  # noqa: F401  — registers the tools before anything imports one
from app.providers import subscription as sub


def test_the_three_subscriptions_people_actually_hold():
    keys = {s.key for s in sub.SUBSCRIPTIONS}
    assert keys == {"codex", "agy", "claude_cli"}
    for s in sub.SUBSCRIPTIONS:
        assert s.install and s.sign_in, f"{s.key} has no way in"
        # The label is what is on their invoice, not our internal name.
        assert s.label and s.key not in s.label.lower()


def test_installed_is_not_signed_in():
    """The whole point of keeping two fields."""
    st = sub.detect("codex")
    assert st.signed_in is None, (
        "detection claimed to know about a sign-in it never checked"
    )
    assert st.ready is False


def test_a_missing_binary_is_told_how_to_install(monkeypatch):
    monkeypatch.setattr(sub, "find_binary", lambda _n: None)
    st = sub.detect("codex")
    assert st.installed is False
    assert "npm install" in st.next_step()


def test_a_cli_in_an_unusual_place_is_still_found(tmp_path, monkeypatch):
    """nvm and ~/.local/bin are not on a service's PATH."""
    fake = tmp_path / "codex"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(sub, "_EXTRA_DIRS", (str(tmp_path),))
    monkeypatch.setattr(sub.shutil, "which", lambda _n: None)
    assert sub.find_binary("codex") == str(fake)
    assert not sub.find_binary("definitely-not-here")


def _installed(monkeypatch, path="/usr/local/bin/codex"):
    monkeypatch.setattr(sub, "find_binary", lambda _n: path)


def test_an_answer_means_signed_in(monkeypatch):
    _installed(monkeypatch)
    st = sub.probe("codex", run=lambda cmd, t: (0, "ok\n", ""))
    assert st.signed_in is True and st.ready is True
    assert st.next_step() == ""


def test_a_signed_out_cli_is_told_to_sign_in(monkeypatch):
    _installed(monkeypatch)
    st = sub.probe(
        "codex", run=lambda cmd, t: (1, "", "Error: not logged in. Run `codex login`.")
    )
    assert st.signed_in is False
    assert "codex login" in st.next_step()


def test_a_spent_allowance_is_not_reported_as_signed_out(monkeypatch):
    """⭐ The loop the customer cannot win: told to sign in, they sign in, it
    still refuses, and the product still says the same thing. A subscription
    that answered "you have used this up" is SIGNED IN — it had to be, to say
    so — and there is nothing for them to do."""
    _installed(monkeypatch)
    for message in (
        "Error: rate limit reached for your plan, try again later",
        "429 Too Many Requests",
        "You've hit your usage limit. Come back in a few hours.",
    ):
        st = sub.probe("codex", run=lambda cmd, t, m=message: (1, "", m))
        assert st.signed_in is True, f"{message!r} was read as a login problem"
        assert "used up" in st.detail
        assert "sign in" not in st.next_step().lower()
        assert "other providers" in st.next_step(), (
            "the customer should be told the work is still getting done"
        )


def test_a_spent_allowance_is_not_a_reason_to_reinstall(monkeypatch):
    _installed(monkeypatch)
    st = sub.probe("codex", run=lambda cmd, t: (1, "", "quota exceeded"))
    assert "npm install" not in st.next_step()


def test_a_timeout_is_not_reported_as_signed_out(monkeypatch):
    """Sending somebody to re-authenticate a working session is a loop with no
    exit — they log in, it times out again, and the product still says no."""
    _installed(monkeypatch)

    def _boom(cmd, t):
        raise TimeoutError("took too long")

    st = sub.probe("codex", run=_boom)
    assert st.signed_in is None, "a busy machine was reported as a login problem"
    assert "log in" not in st.next_step().lower()


def test_ran_but_said_nothing_is_unclear_not_signed_out(monkeypatch):
    _installed(monkeypatch)
    st = sub.probe("codex", run=lambda cmd, t: (0, "   ", ""))
    assert st.signed_in is None
    assert "unclear" in st.detail


def test_the_probe_asks_the_cli_the_vendor_way(monkeypatch):
    """Each CLI takes its prompt differently; one shape for all would look
    like a signed-out failure on two of the three."""
    _installed(monkeypatch, "/bin/codex")
    seen: list = []
    sub.probe("codex", run=lambda cmd, t: (seen.append(cmd), (0, "ok", ""))[1])
    assert seen[0][:2] == ["/bin/codex", "exec"]

    _installed(monkeypatch, "/bin/agy")
    seen.clear()
    sub.probe("agy", run=lambda cmd, t: (seen.append(cmd), (0, "ok", ""))[1])
    assert seen[0][:2] == ["/bin/agy", "-p"]


def test_an_unknown_key_does_not_raise():
    st = sub.detect("nope")
    assert st.installed is False and st.ready is False


def test_nothing_here_stores_a_credential():
    """The customer's session stays theirs; ABS only calls the binary."""
    src = open(os.path.join(os.path.dirname(sub.__file__), "subscription.py")).read()
    for forbidden in ("password", "token=", "api_key", "secret"):
        assert forbidden not in src.lower(), (
            f"the subscription path started handling {forbidden!r} — it must "
            "only ever run a binary the customer signed into themselves"
        )


# --- yüzey: yetenek okuması + isteğe bağlı kontrol ---------------------------


def _status() -> dict:
    import asyncio
    import json

    import app.mcp.server  # noqa: F401  (registers the tools)
    from app.mcp.tools import capability_tools

    return json.loads(asyncio.run(capability_tools.capability_status()))


def test_the_readout_lists_what_they_already_pay_for(monkeypatch):
    from app.mcp.tools import capability_tools

    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    rows = _status().get("subscriptions")
    assert isinstance(rows, list) and rows, "the editor has nothing to show"
    keys = {r["key"] for r in rows}
    assert keys == {"codex", "agy", "claude_cli"}
    for r in rows:
        # Never "ready" from a readout: nobody has been asked to sign in.
        assert r["ready"] is False or r["signed_in"] is True
        assert r["next_step"] or r["ready"]


def test_the_readout_never_spends_their_allowance(monkeypatch):
    """Detection is a file-system check. Probing costs a real call, so a page
    load must not do it — the customer would learn to avoid the page."""
    from app.providers import subscription as sub

    called = []
    monkeypatch.setattr(sub, "probe", lambda *a, **k: called.append(a))
    from app.mcp.tools import capability_tools

    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    _status()
    assert called == [], "opening a panel spent the customer's subscription"


def test_the_check_tool_reports_what_the_probe_found(monkeypatch):
    import asyncio
    import json

    import app.mcp.server  # noqa: F401
    from app.mcp.tools import capability_tools
    from app.providers import subscription as sub

    monkeypatch.setattr(sub, "find_binary", lambda _n: "/bin/codex")
    monkeypatch.setattr(
        sub, "_run", lambda cmd, t: (1, "", "Error: not logged in. Run `codex login`.")
    )

    out = json.loads(asyncio.run(capability_tools.subscription_check("codex")))
    assert out["ok"] is True
    assert out["installed"] is True and out["signed_in"] is False
    assert "codex login" in out["next_step"]


def test_the_check_tool_survives_a_broken_probe(monkeypatch):
    import asyncio
    import json

    import app.mcp.server  # noqa: F401
    from app.mcp.tools import capability_tools

    out = json.loads(asyncio.run(capability_tools.subscription_check("")))
    assert out["ok"] is True and out["installed"] is False
