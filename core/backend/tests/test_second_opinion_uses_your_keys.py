# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The second opinion has to be available to the person who paid for it.

Differentiator #3 in the pivot document is the uncertainty flag: ask several
models, and when they part ways, say so instead of picking one and sounding
sure. `ask_disagree` is its first concrete form in the editor.

Audited 2026-08-02, it could not run on the install we actually sell. Three
providers were hard-coded, and the call went straight to the adapter with no
key attached — the exact failure `app/providers/byok.py` was written to stop:

    "anything that talks to an adapter directly must ask here, or the
     promotion is a promise the credential never keeps."

So a developer who pasted an Anthropic key and asked for a second opinion got
"no provider answered". Not degraded — absent, on a product whose entire model
is that you bring your own keys.

Two subtler faults are pinned here too, because both are the kind that read as
working:

* one answer rendered as a comparison. Zero answers already said "this is not
  agreement"; one answer said nothing at all, and one opinion presented where
  two were asked for is the more convincing lie;
* a footnote claiming Jaccard every time, including runs that used embeddings.
"""

from __future__ import annotations

import pytest

from app.disagreement import detector


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Provider:
    """Answers only when handed a key, which is what an adapter really does."""

    def __init__(self, text: str, *, needs_key: bool = True) -> None:
        self._text = text
        self._needs_key = needs_key
        self.seen_keys: list[str | None] = []

    async def call(self, prompt: str, model=None, **kwargs):  # noqa: ANN001
        key = kwargs.get("api_key")
        self.seen_keys.append(key)
        if self._needs_key and not key:
            raise RuntimeError("no credentials")
        return _Resp(self._text)


@pytest.fixture(autouse=True)
def _no_leftovers():
    """The detector remembers its last run so the dashboard can show it. That
    memory is module state, and a test that leaves some behind changes the
    answer another file gets — which is a failure about test order, not code."""
    detector._last.clear()
    yield
    detector._last.clear()


@pytest.fixture
def byok_install(monkeypatch):
    """One person, two keys of their own, and a server that has none."""
    providers = {
        "anthropic": _Provider("Use a lock around the counter."),
        "gemini": _Provider("Wrap the counter in a mutex."),
        "groq": _Provider("never reached"),
    }
    monkeypatch.setattr(detector, "get_provider", lambda n: providers[n])
    monkeypatch.setattr(
        detector, "byok_providers", lambda *_a, **_k: frozenset({"anthropic", "gemini"})
    )
    monkeypatch.setattr(
        detector,
        "owner_key_for",
        lambda p, **_k: {"anthropic": "sk-ant-x", "gemini": "AIza-y"}.get(p),
    )
    monkeypatch.setattr(
        detector, "get_active_providers", lambda **_k: ["anthropic", "gemini"]
    )
    return providers


@pytest.mark.asyncio
async def test_it_runs_on_the_keys_the_caller_brought(byok_install):
    out = await detector.ask_disagree(
        "How do I make this counter thread-safe?", tenant_id="acme", user_subject="enes"
    )
    assert out["status"] == "ok", "a BYOK install got no second opinion at all"
    assert set(out["models"]) == {"anthropic", "gemini"}
    # The key has to travel with the call, or the choice of provider is decor.
    assert byok_install["anthropic"].seen_keys == ["sk-ant-x"]
    assert byok_install["gemini"].seen_keys == ["AIza-y"]


@pytest.mark.asyncio
async def test_it_does_not_ask_providers_the_caller_cannot_use(byok_install):
    await detector.ask_disagree("q", tenant_id="acme", user_subject="enes")
    assert byok_install["groq"].seen_keys == [], (
        "a provider with no key was called anyway — that is a guaranteed failure "
        "spent as a real request"
    )


@pytest.mark.asyncio
async def test_one_answer_is_not_a_second_opinion(monkeypatch):
    only_one = {
        "anthropic": _Provider("Use a lock."),
        "gemini": _Provider("", needs_key=False),  # answers, but says nothing
    }
    monkeypatch.setattr(detector, "get_provider", lambda n: only_one[n])
    # The caller brought the anthropic key — a paid provider runs on the key
    # of the person asking (2026-08-18), so it stays in the chain here.
    monkeypatch.setattr(detector, "byok_providers", lambda *_a, **_k: frozenset({"anthropic"}))
    monkeypatch.setattr(detector, "owner_key_for", lambda p, **_k: "k")
    monkeypatch.setattr(
        detector, "get_active_providers", lambda **_k: ["anthropic", "gemini"]
    )

    out = await detector.ask_disagree("q", tenant_id="acme")
    assert out["status"] == "single", (
        "one answer was reported as a completed comparison — the reader would "
        "take a single opinion for a confirmed one"
    )
    assert out["consensus_score"] is None
    assert out["models"] == ["anthropic"]
    assert out["asked"] == ["anthropic", "gemini"], "the panel cannot say who went quiet"


@pytest.mark.asyncio
async def test_nobody_answered_is_still_not_agreement(monkeypatch):
    monkeypatch.setattr(
        detector, "get_provider", lambda n: _Provider("x")  # needs a key, gets none
    )
    monkeypatch.setattr(detector, "byok_providers", lambda *_a, **_k: frozenset())
    monkeypatch.setattr(detector, "owner_key_for", lambda p, **_k: None)
    monkeypatch.setattr(detector, "get_active_providers", lambda **_k: ["groq"])

    out = await detector.ask_disagree("q")
    assert out["status"] == "empty"
    assert out["consensus_score"] is None


@pytest.mark.asyncio
async def test_an_install_with_one_provider_says_so_instead_of_failing(monkeypatch):
    """The honest answer to "you only have one key" is not an error."""
    monkeypatch.setattr(detector, "get_provider", lambda n: _Provider("a", needs_key=False))
    monkeypatch.setattr(detector, "byok_providers", lambda *_a, **_k: frozenset({"groq"}))
    monkeypatch.setattr(detector, "owner_key_for", lambda p, **_k: None)
    monkeypatch.setattr(detector, "get_active_providers", lambda **_k: ["groq"])

    out = await detector.ask_disagree("q", tenant_id="acme")
    assert out["status"] == "single"
    assert "one provider" in out["note"].lower()


@pytest.mark.asyncio
async def test_the_footnote_describes_the_run_that_happened(monkeypatch):
    """It used to claim Jaccard unconditionally, including on embedding runs."""
    two = {
        "anthropic": _Provider("aaa bbb", needs_key=False),
        "gemini": _Provider("aaa ccc", needs_key=False),
    }
    monkeypatch.setattr(detector, "get_provider", lambda n: two[n])
    monkeypatch.setattr(detector, "byok_providers", lambda *_a, **_k: frozenset({"anthropic"}))
    monkeypatch.setattr(detector, "owner_key_for", lambda p, **_k: None)
    monkeypatch.setattr(
        detector, "get_active_providers", lambda **_k: ["anthropic", "gemini"]
    )

    out = await detector.ask_disagree("q")
    assert "word overlap" in out["note"].lower()
    assert out["similarity_basis"] == "jaccard"
    assert out["consensus_score"] is not None


@pytest.mark.asyncio
async def test_two_answers_from_one_provider_would_not_be_a_second_opinion(monkeypatch):
    """Agreement between siblings proves little — the detector's own rule."""
    seen: list[str] = []

    def _get(n):
        seen.append(n)
        return _Provider("same", needs_key=False)

    monkeypatch.setattr(detector, "get_provider", _get)
    monkeypatch.setattr(detector, "byok_providers", lambda *_a, **_k: frozenset())
    monkeypatch.setattr(detector, "owner_key_for", lambda p, **_k: None)
    monkeypatch.setattr(
        detector, "get_active_providers", lambda **_k: ["groq", "groq", "cerebras"]
    )

    await detector.ask_disagree("q")
    assert len(seen) == len(set(seen)), "the same provider was asked twice"


@pytest.mark.asyncio
async def test_the_run_is_recorded_without_the_question(byok_install):
    """`/api/disagreement/latest` was a permanent empty payload because nobody
    kept the result. It is kept now — minus the answers, which belong to the
    person who asked and not to an operator's dashboard."""
    await detector.ask_disagree("q", tenant_id="acme", user_subject="enes")
    try:
        run = detector.last_run("acme")
        assert run is not None, "the endpoint would show 'empty' after a real run"
        assert run["consensus_score"] is not None
        assert "responses" not in run
        assert run["last_call_at"]
        assert detector.last_run("someone-else") is None
    finally:
        detector._last.pop("acme", None)


@pytest.mark.asyncio
async def test_the_mcp_tool_actually_passes_the_caller(monkeypatch):
    """The detector can be perfect and still be handed nothing.

    That is the failure mode that survives a green suite: the tool forgets to
    look up who is calling, every install behaves like an anonymous one, and
    the BYOK path is dead again with no test noticing.
    """
    import app.mcp.server  # noqa: F401  (registers the tools)
    from app.mcp.tools import quality

    seen: dict = {}

    async def _spy(prompt, analyzer_model=None, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return {"status": "empty", "models": []}

    monkeypatch.setattr(quality, "_ask_disagree_impl", _spy)
    monkeypatch.setattr(
        "app.mcp.context.get_mcp_caller", lambda: ("acme", "enes"), raising=False
    )

    await quality.ask_disagree("does this deadlock?")
    assert seen.get("tenant_id") == "acme", "the tool never asked who was calling"
    assert seen.get("user_subject") == "enes"
