# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Subscriptions people already pay for, connected without an API key.

Most developers arriving at ABS have a ChatGPT Plus, Claude Pro or Google AI
Pro subscription and no API key at all. Those are different products: a
subscription buys the chat app, not API credit, so there is nothing to paste
into a key box. The customer reaches the settings page, finds no way in, and
concludes the product does not support what they are paying for.

Each of those vendors ships an official CLI that the subscription covers, and
each can run headless once its owner has signed in. So the path exists — it is
just shaped differently: install a binary, sign in once in a browser, and ABS
calls it. No key travels, no credential is stored here, and the account stays
the customer's.

Two facts are kept apart on purpose, because collapsing them is how a settings
page lies:

* **installed** — the binary is on this machine. Cheap to check, always true
  or false.
* **signed in** — it will actually answer. Only a probe can tell, the probe
  costs a real call, and until it has run the answer is *unknown*. An
  installed-but-signed-out CLI reported as ready is the same defect as a
  mistyped key stored with a green tick (07-31).

Self-hosted only, and that is inherent: the binary and the browser session live
on the machine the customer controls. There is no version of this where we hold
the session for them, which is also why it is defensible — the customer runs
the vendor's own tool under their own account.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Subscription:
    """One vendor CLI ABS knows how to drive."""

    key: str
    # What the customer calls it — the words on their invoice, not ours.
    label: str
    binary: str
    install: str
    sign_in: str
    # Startup is seconds, not milliseconds: these belong on the deep work, not
    # on keystroke-latency paths like Tab.
    slow_start: bool = True


SUBSCRIPTIONS: tuple[Subscription, ...] = (
    Subscription(
        key="codex",
        label="ChatGPT Plus / Pro",
        binary="codex",
        install="npm install -g @openai/codex",
        sign_in="codex login",
    ),
    Subscription(
        key="agy",
        label="Google AI Pro",
        binary="agy",
        install="curl -fsSL https://antigravity.google/cli/install.sh | bash",
        sign_in="agy",
    ),
    Subscription(
        key="claude_cli",
        label="Claude Pro / Max",
        binary="claude",
        install="npm install -g @anthropic-ai/claude-code",
        sign_in="claude",
    ),
)

BY_KEY = {s.key: s for s in SUBSCRIPTIONS}

# Extra places to look. A CLI installed through nvm or a user-local prefix is
# not on the PATH of a service started by systemd, and "not found" would be
# wrong rather than merely unhelpful.
_EXTRA_DIRS = (
    os.path.expanduser("~/.local/bin"),
    "/usr/local/bin",
    "/opt/homebrew/bin",
)


def find_binary(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for d in _EXTRA_DIRS:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


@dataclass(frozen=True)
class Status:
    key: str
    label: str
    installed: bool
    path: Optional[str]
    # None until somebody probes. Not False — "we have not asked" and "it said
    # no" are different answers and only one of them is the customer's problem.
    signed_in: Optional[bool]
    detail: str
    install: str
    sign_in: str

    @property
    def ready(self) -> bool:
        return self.installed and self.signed_in is True

    def next_step(self) -> str:
        """The one sentence that turns this row into something to do."""
        if not self.installed:
            return f"Install it: {self.install}"
        if self.signed_in is None:
            return "Installed. Check the sign-in to confirm it can answer."
        if not self.signed_in:
            return f"Installed, but signed out. Run: {self.sign_in}"
        if "used up" in self.detail:
            # Nothing to do — and saying so is the point. The alternative was
            # sending somebody to re-authenticate a session that is fine.
            return (
                "Connected. Its allowance is spent for the moment; ABS is using "
                "your other providers until it frees up."
            )
        return ""


def detect(key: str) -> Status:
    """Is it here? Cheap, and it does not claim to know about the sign-in."""
    sub = BY_KEY.get(key)
    if sub is None:
        return Status(key, key, False, None, None, "unknown subscription", "", "")
    path = find_binary(sub.binary)
    return Status(
        key=sub.key,
        label=sub.label,
        installed=path is not None,
        path=path,
        signed_in=None,
        detail="found" if path else f"`{sub.binary}` is not on this machine",
        install=sub.install,
        sign_in=sub.sign_in,
    )


def detect_all() -> list[Status]:
    return [detect(s.key) for s in SUBSCRIPTIONS]


# The probe asks the CLI to answer something trivial. It costs one call against
# the customer's own subscription, which is why it is never run as part of a
# page load — only when somebody asks "is this working?".
_PROBE_PROMPT = "Reply with the single word: ok"
_PROBE_TIMEOUT = 60


def _probe_command(sub: Subscription, path: str) -> list[str]:
    if sub.key == "codex":
        return [path, "exec", "--skip-git-repo-check", _PROBE_PROMPT]
    if sub.key == "agy":
        return [path, "-p", _PROBE_PROMPT]
    return [path, "-p", _PROBE_PROMPT]


# Spent for now, not signed out. These are different problems with different
# answers, and getting them the wrong way round is a loop the customer cannot
# win: told to sign in, they sign in, it still refuses, and the product still
# says the same thing. Subscription CLIs are limited by a rolling window rather
# than a daily count, so the honest sentence is "not right now" — a countdown
# would be arithmetic we cannot do and do not need.
_RATE_LIMITED_MARKERS = (
    "rate limit",
    "rate_limit",
    "usage limit",
    "quota",
    "too many requests",
    "429",
    "try again later",
    "limit reached",
    "you've hit",
    "come back",
)

_SIGNED_OUT_MARKERS = (
    "not logged in",
    "not signed in",
    "please log in",
    "please sign in",
    "unauthorized",
    "authentication",
    "login required",
    "run `codex login`",
    "no credentials",
    "session expired",
)


def probe(key: str, *, run: Optional[Callable] = None) -> Status:
    """Ask the CLI to answer, and report what actually happened.

    A failure is read carefully rather than flattened to "not working": a
    signed-out CLI needs a login, a missing one needs an install, and a CLI
    that timed out needs neither — telling a customer to log in again because
    the machine was busy sends them round a loop they cannot win.
    """
    base = detect(key)
    if not base.installed or not base.path:
        return base
    sub = BY_KEY[key]
    runner = run or _run
    try:
        code, out, err = runner(_probe_command(sub, base.path), _PROBE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — a probe must not take a page down
        logger.info("subscription probe failed for %s: %s", key, exc)
        return _with(base, None, f"could not run {sub.binary}: {str(exc)[:80]}")

    blob = f"{out}\n{err}".lower()
    if code == 0 and out.strip():
        return _with(base, True, "answered")
    if any(m in blob for m in _RATE_LIMITED_MARKERS):
        # Signed in — it said so by telling us we had used it up.
        return _with(base, True, "connected, but used up for now")
    if any(m in blob for m in _SIGNED_OUT_MARKERS):
        return _with(base, False, "signed out")
    if code == 0:
        # Ran, said nothing. Not a sign-in problem, and calling it one would
        # send the customer to re-authenticate something that authenticated.
        return _with(base, None, "ran but returned nothing — unclear")
    return _with(base, None, (err or out).strip()[:120] or f"exit {code}")


def _with(s: Status, signed_in: Optional[bool], detail: str) -> Status:
    return Status(
        key=s.key,
        label=s.label,
        installed=s.installed,
        path=s.path,
        signed_in=signed_in,
        detail=detail,
        install=s.install,
        sign_in=s.sign_in,
    )


def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    p = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=timeout, cwd="/tmp"
    )
    return p.returncode, p.stdout, p.stderr
