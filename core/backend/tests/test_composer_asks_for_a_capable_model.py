# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The Composer must not run on whatever model the adapter defaults to.

Found by the effectiveness harness, 2026-08-02. The Composer asked for a change
and got nothing; the server said

    413 Request too large for model `llama-3.1-8b-instant`

`call_with_cascade` is called with no model, so every adapter falls back to its
`default_model`, and Groq's is an 8-billion-parameter instant model — small,
cheap, and the first provider in the default free-first chain. So on a fresh
free-tier install the product's flagship feature was running on the weakest
model the account has, against a prompt carrying up to 14k characters of
workspace. It answered with a 413, or with JSON its own validator rejected.

The judge already solved this: `_JUDGE_ROUTES` pins a capable model per
provider so scores stay comparable. The Composer needs the same thing for a
different reason — a multi-file edit is the hardest thing the product asks a
model to do, and the default was the one least able to do it.

Pinned here:

* a provider we know a capable model for gets it, by name;
* a provider we do not know keeps its own default — guessing a model name is
  how a working key starts returning 404;
* the choice never depends on which provider happens to lead the chain.
"""

from __future__ import annotations

import pytest

from app.composer import runtime


def test_a_known_provider_gets_a_capable_model():
    assert runtime.model_for("groq") == "openai/gpt-oss-120b"
    assert runtime.model_for("cerebras") == "gpt-oss-120b"


def test_the_weak_default_is_not_what_we_ask_for():
    """The whole finding in one line: groq's adapter default is the small
    fast model (was the 8B; since 2026-08-18 gpt-oss-20b, same role)."""
    from app.providers.registry import get_registry

    assert get_registry()["groq"].default_model == "openai/gpt-oss-20b"
    assert runtime.model_for("groq") != "openai/gpt-oss-20b"


def test_an_unknown_provider_keeps_its_own_default():
    """Inventing a model name is how a perfectly good key returns 404."""
    assert runtime.model_for("some-new-provider") is None
    assert runtime.model_for("") is None


def test_every_pinned_model_is_one_that_provider_actually_serves():
    """A pin that names a model the provider does not have is worse than no
    pin: it turns a working provider into a permanent 404."""
    from app.providers.groq.v1 import SUPPORTED_MODELS as GROQ

    assert runtime.model_for("groq") in GROQ


@pytest.mark.asyncio
async def test_the_cascade_is_asked_for_the_pinned_model(monkeypatch):
    seen: dict = {}

    async def _fake(prompt, **kwargs):  # noqa: ANN001
        seen.update(kwargs)

        class _R:
            text = '{"summary": "", "edits": []}'
            provider = "groq"
            providers_tried = ["groq"]
            tokens_in = tokens_out = 0
            model = kwargs.get("model")

        return _R()

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["groq", "cerebras"]
    )

    await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    models = seen.get("models") or {}
    assert models.get("groq") == "openai/gpt-oss-120b", (
        "the cascade was left to pick, which means the adapter default"
    )
    assert seen.get("model") is None, (
        "one model name was forced on the whole chain — every fallback leg "
        "would 404 on a model it does not serve"
    )
