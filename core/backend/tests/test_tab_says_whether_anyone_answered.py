# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""An empty completion has two causes and the editor has to be told which.

`complete()` returns `{"text": ""}` when the model looked at the cursor and had
nothing worth adding, and also when no provider answered at all — a rate limit,
a timeout, a model retired upstream. Same shape, opposite meanings.

The editor caches what it is given, because Tab runs at keystroke frequency and
a re-trigger at the same spot has to be free. So until 2026-08-06 one bad
minute was remembered as the answer: every cursor position visited while a
provider was rate-limited stopped completing for the rest of the session, and
those are precisely the positions the developer is about to return to. Nothing
in the product said so — Tab is silent by design, and this is what a silent
feature failing looks like.

`ok` is the distinction, at the only layer that knows it. The editor caches an
empty answer when a provider gave one, and does not when none did.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_a_real_answer_says_somebody_answered(monkeypatch):
    from app.fim import complete as fim

    class _Resp:
        text = "return 1\n"
        model = "m"
        tokens_in = 5
        tokens_out = 3

    class _Provider:
        async def call(self, *_a, **_k):
            return _Resp()

    # The chain is a list of provider NAMES; the adapter is fetched per name.
    # My first version of this stub returned (name, callable) pairs and the
    # test failed against correct code — worth keeping in mind before reading
    # a red test as a defect.
    monkeypatch.setattr(fim, "_free_fast_chain", lambda *_a, **_k: ["groq"])
    monkeypatch.setattr(fim, "_FAST_MODELS", {"groq": "m"}, raising=False)
    monkeypatch.setattr(
        "app.providers.registry.get_provider", lambda _n: _Provider(), raising=False
    )

    out = await fim.complete("def f():\n    ", "", language="python")
    assert out.get("ok") is True, (
        "a completion the provider actually produced is not marked as answered, "
        "so the editor cannot tell it from an outage"
    )


@pytest.mark.asyncio
async def test_no_provider_says_nobody_answered():
    """The state a fresh install with no keys is in."""
    from app.fim import complete as fim

    out = await fim.complete("", "")
    assert out["text"] == ""
    assert out.get("ok") is False, (
        "an empty prefix returns an unmarked empty answer, which the editor "
        "would remember as this position's completion"
    )


@pytest.mark.asyncio
async def test_a_model_that_had_nothing_to_add_still_counts_as_an_answer(monkeypatch):
    """The third state, and the one that is easy to lose.

    Tab is silent at plenty of cursor positions for perfectly good reasons —
    mid-word, after a closing brace, where the suffix already says what the
    model would. The loop treats an empty completion as "try the next
    provider", so that outcome leaves by the same door as a total outage.

    If those two are conflated the fix for one breaks the other: mark both
    cached and an outage sticks; mark neither and Tab re-asks at every typing
    pause in a position where the answer is known to be nothing.
    """
    from app.fim import complete as fim

    class _Empty:
        text = ""
        model = "m"
        tokens_in = 4
        tokens_out = 0

    class _Provider:
        async def call(self, *_a, **_k):
            return _Empty()

    monkeypatch.setattr(fim, "_free_fast_chain", lambda *_a, **_k: ["groq"])
    monkeypatch.setattr(fim, "_FAST_MODELS", {"groq": "m"}, raising=False)
    monkeypatch.setattr(
        "app.providers.registry.get_provider", lambda _n: _Provider(), raising=False
    )

    out = await fim.complete("x = 1\n", "", language="python")
    assert out["text"] == ""
    assert out.get("ok") is True, (
        "a provider answered and had nothing to add, and the reply says nobody "
        "answered — so Tab will ask again at this position on every pause"
    )


@pytest.mark.asyncio
async def test_a_provider_that_threw_does_not_count_as_an_answer(monkeypatch):
    from app.fim import complete as fim

    class _Broken:
        async def call(self, *_a, **_k):
            raise RuntimeError("rate limited")

    monkeypatch.setattr(fim, "_free_fast_chain", lambda *_a, **_k: ["groq"])
    monkeypatch.setattr(fim, "_FAST_MODELS", {"groq": "m"}, raising=False)
    monkeypatch.setattr(
        "app.providers.registry.get_provider", lambda _n: _Broken(), raising=False
    )

    out = await fim.complete("x = 1\n", "", language="python")
    assert out["text"] == ""
    assert out.get("ok") is False, (
        "an outage is being reported as a real empty answer, which the editor "
        "will remember for the rest of the session"
    )


def test_every_return_path_says_which_it_is():
    """Read from the source, because the failure is a path nobody exercised.

    The chain-exhausted return is reached only when every provider fails in
    sequence, which is exactly the case a unit test tends not to reach and the
    customer reaches on a bad afternoon. Counting the returns is cruder than
    calling them and it cannot miss one.
    """
    import inspect
    import re

    from app.fim import complete as fim

    source = inspect.getsource(fim.complete)
    returns = re.findall(r"return \{[^}]*\}", source, re.DOTALL)
    assert returns, "complete() no longer returns dict literals; re-read this test"
    missing = [r.replace("\n", " ")[:70] for r in returns if '"ok"' not in r]
    assert missing == [], (
        "a return path does not say whether anyone answered, so the editor will "
        "cache it as an answer:\n  " + "\n  ".join(missing)
    )
