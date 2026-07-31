# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Tab / fill-in-the-middle completion.

The free tier is chat models, not FIM models: they answer "fill the gap" by
echoing the whole line or running on into the suffix. The insertion is
recovered deterministically, so these tests pin that recovery — the part of
autocomplete that decides whether a completion helps or gets in the way.
"""

from __future__ import annotations

import asyncio

from app.fim import complete as fim


def test_a_whole_line_echo_is_trimmed_to_the_insertion():
    # Cursor after "return "; the model replays the whole line.
    prefix = "def add(a, b):\n    return "
    raw = "return a + b"
    assert fim._clean(raw, prefix, "\n") == "a + b"


def test_the_indented_line_start_is_stripped_too():
    prefix = "def add(a, b):\n    return "
    raw = "    return a + b"  # replayed with the indentation
    assert fim._clean(raw, prefix, "\n") == "a + b"


def test_a_multiline_replay_of_the_prefix_is_trimmed_to_the_insertion():
    # Seen live (07-31): the model restated the WHOLE snippet from the top,
    # not just the current line — the single-line echo handling never fired
    # and the ghost text duplicated the entire function at the cursor.
    prefix = "def fibonacci(n):\n    if n <= 1:\n        return n\n    return "
    raw = (
        "def fibonacci(n):\n    if n <= 1:\n        return n\n"
        "    return fibonacci(n-1) + fibonacci(n-2)"
    )
    assert fim._clean(raw, prefix, "\n") == "fibonacci(n-1) + fibonacci(n-2)"


def test_a_short_accidental_overlap_is_not_an_echo():
    # The completion legitimately starts with characters that also end the
    # prefix; without a line break in the overlap nothing is stripped here,
    # and the current-line rule below decides.
    prefix = "x = re"
    raw = "result + 1"
    assert fim._clean(raw, prefix, "\n") == "result + 1"


def test_a_fence_never_reaches_the_buffer():
    assert fim._clean("```python\na + b\n```", "x = ", "\n") == "a + b"


def test_the_completion_stops_before_repeating_the_suffix():
    # The suffix already has the closing line; the model runs on into it.
    prefix = "items = [\n    "
    suffix = "\n]\nprint(items)"
    raw = "1,\n    2,\n    3,\nprint(items)"
    out = fim._clean(raw, prefix, suffix)
    assert "print(items)" not in out
    assert "1," in out


def test_a_whitespace_only_completion_is_nothing():
    assert fim._clean("   \n  ", "x = ", "") == ""


def test_multiline_only_on_an_empty_line():
    assert fim.multiline_ok("def f():\n    ") is True
    assert fim.multiline_ok("    return ") is False


def test_a_dead_first_provider_does_not_silence_tab(monkeypatch):
    """Live (08-01): cerebras' pinned model was retired upstream, BYOK put
    cerebras first, and Tab went silent — one provider was a single point of
    silence. The second one now gets its turn."""
    monkeypatch.setattr(fim, "_free_fast_chain", lambda *a, **k: ["cerebras", "groq"])

    class _Dead:
        async def call(self, *a, **k):
            raise RuntimeError("model_not_found")

    class _Alive:
        async def call(self, *a, **k):
            return type("R", (), {"text": "a + b", "model": "m", "tokens_out": 3})()

    monkeypatch.setattr(
        "app.providers.registry.get_provider",
        lambda name: _Dead() if name == "cerebras" else _Alive(),
    )
    out = asyncio.run(fim.complete("def add(a, b):\n    return ", "\n"))
    assert out["provider"] == "groq", out
    assert out["text"] == "a + b"


def test_an_empty_answer_also_hands_over(monkeypatch):
    """A reasoning model that spends its whole budget thinking returns 200 and
    nothing. That is not an outage, but it is not a completion either."""
    monkeypatch.setattr(fim, "_free_fast_chain", lambda *a, **k: ["cerebras", "groq"])

    class _Silent:
        async def call(self, *a, **k):
            return type("R", (), {"text": "", "model": "m"})()

    class _Alive:
        async def call(self, *a, **k):
            return type("R", (), {"text": "a + b", "model": "m"})()

    monkeypatch.setattr(
        "app.providers.registry.get_provider",
        lambda name: _Silent() if name == "cerebras" else _Alive(),
    )
    out = asyncio.run(fim.complete("def add(a, b):\n    return ", "\n"))
    assert out["provider"] == "groq"
    assert out["text"] == "a + b"


def test_the_pinned_completion_models_are_named_not_guessed():
    """A stale model id is invisible until the provider is promoted. Pin the
    two we measured so a silent edit has to argue with a test."""
    assert fim._FAST_MODELS["groq"] == "llama-3.1-8b-instant"
    assert fim._FAST_MODELS["cerebras"] == "gemma-4-31b"


def test_no_fast_free_provider_returns_empty_not_error(monkeypatch):
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **_: [])
    out = asyncio.run(fim.complete("def f():\n    return ", "\n"))
    assert out["text"] == ""
    assert out["provider"] == ""


def test_a_blank_prefix_does_not_call_a_model(monkeypatch):
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not be called on a blank prefix")

    monkeypatch.setattr("app.providers.registry.get_provider", _boom)
    out = asyncio.run(fim.complete("   \n  ", ""))
    assert out["text"] == ""
    assert called["n"] == 0


def test_a_provider_error_is_a_silent_miss(monkeypatch):
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_: ["groq"]
    )

    class _P:
        async def call(self, *_a, **_k):
            raise RuntimeError("upstream 503")

    monkeypatch.setattr("app.providers.registry.get_provider", lambda _n: _P())
    out = asyncio.run(fim.complete("def f():\n    return ", "\n"))
    assert out["text"] == "", "a failed completion is empty, never an error"


def test_the_completion_is_pinned_to_the_free_tier(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **kw: (seen.update(kw) or ["groq"]),
    )

    class _P:
        async def call(self, prompt, **kw):
            class _R:
                text = "a + b"

            return _R()

    monkeypatch.setattr("app.providers.registry.get_provider", lambda _n: _P())
    out = asyncio.run(fim.complete("x = ", ""))
    assert seen.get("skip_paid") is True, "autocomplete never uses a paid provider"
    assert out["tier"] == "free"
