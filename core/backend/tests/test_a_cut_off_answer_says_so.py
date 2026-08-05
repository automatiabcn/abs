# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Every provider says when it ran out of room. Nothing read it.

The truncation defect has been chased twice now with a ruler. On 2026-08-02
Composer was measured turning cut-off replies into clean, applicable deletions
(+20/-784 among them) and the repair was a ratio: an answer that lost more than
half a file is refused. On 08-05 the same ratio was extended to model-written
diffs, because that door had no check at all.

A ratio is a guess. It refuses a real refactor that removes 60% of a file, and
it accepts a reply cut off at the 45% mark. Both mistakes are avoidable,
because the thing being guessed at is reported: OpenAI-compatible providers
return `finish_reason: "length"`, Anthropic returns `stop_reason: "max_tokens"`,
Gemini returns `finishReason: "MAX_TOKENS"`. Every provider ABS ships with
answers the question directly.

`base.py` read `content` and `usage` and dropped the rest. So the product had
the evidence in hand on every call, discarded it, and then inferred it back
from line counts.

This matters most where the cap is smallest. ⌘K asks the model to return the
whole selection with `max_tokens: 1500` — around a hundred and fifty lines of
code. Select more than that and the reply is cut off by construction, and the
editor offers the short version as a graded, accept-ready replacement for the
developer's selection.
"""

from __future__ import annotations

import pytest


def _openai_like(finish: str | None) -> dict:
    return {
        "choices": [{"message": {"content": "def f():\n    return 1\n"}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_the_response_can_carry_the_fact():
    from app.providers.schemas import ProviderResponse

    assert hasattr(ProviderResponse(), "truncated"), (
        "a provider answer has nowhere to record that it was cut off, so the "
        "one honest signal is dropped at the boundary"
    )
    assert ProviderResponse().truncated is False, (
        "unknown must default to 'not truncated' — a default of True would "
        "refuse every answer from a provider that says nothing"
    )


@pytest.mark.parametrize(
    "finish,expected",
    [
        ("length", True),
        ("max_tokens", True),
        ("MAX_TOKENS", True),
        ("stop", False),
        ("", False),
        (None, False),
    ],
)
def test_finish_reasons_are_read_the_same_way_whatever_they_are_spelled(finish, expected):
    """Four providers, four spellings, one question.

    Case and underscores differ between vendors; the meaning does not. Getting
    this wrong in one direction silently turns the guard off for that provider.
    """
    from app.providers.base import was_cut_off

    assert was_cut_off(finish) is expected


def test_a_truncated_openai_style_reply_is_flagged():
    from app.providers.base import read_openai_payload

    res = read_openai_payload(_openai_like("length"), provider="groq", model="m", elapsed_ms=1)
    assert res.truncated is True
    assert res.text, "the text is still returned — the caller decides what to do"


def test_a_complete_reply_is_not_flagged():
    from app.providers.base import read_openai_payload

    res = read_openai_payload(_openai_like("stop"), provider="groq", model="m", elapsed_ms=1)
    assert res.truncated is False


def test_a_provider_that_says_nothing_is_not_assumed_truncated():
    """Silence is not evidence.

    A provider that omits the field must not have every answer refused — that
    would take a working chain off the air for a reason nobody could see.
    """
    from app.providers.base import read_openai_payload

    payload = {"choices": [{"message": {"content": "hi"}}], "usage": {}}
    res = read_openai_payload(payload, provider="ollama", model="m", elapsed_ms=1)
    assert res.truncated is False


def test_anthropic_and_gemini_spellings_are_covered():
    """The two vendors that do not use `finish_reason` at all.

    Checked at the adapter rather than in the abstract: a helper that handles
    every spelling is worth nothing if the adapter never calls it.
    """
    import inspect

    from app.providers.anthropic import adapter as anthropic_adapter
    from app.providers.gemini import adapter as gemini_adapter

    a = inspect.getsource(anthropic_adapter)
    g = inspect.getsource(gemini_adapter)
    assert "stop_reason" in a and "truncated" in a, (
        "the Anthropic adapter does not read stop_reason, so a cut-off answer "
        "from Claude arrives looking complete"
    )
    assert "finishReason" in g and "truncated" in g, (
        "the Gemini adapter does not read finishReason, so a cut-off answer "
        "from Gemini arrives looking complete"
    )


def test_a_cut_off_generation_refuses_edits_that_look_perfectly_whole(tmp_path, monkeypatch):
    """The wiring, not the helper.

    This is the case the ratio guards cannot see and the one my own first
    attempt got wrong: a truncated answer still yields a well-formed edit, so a
    check that reads the built diff never fires. The refusal has to be asked
    before the diff is built.

    Both edits here would apply cleanly. The generation stopped at the token
    limit, so neither is trustworthy — the file being written when the room ran
    out is not identifiable from here.
    """
    import asyncio

    from app.codegraph import graph as codegraph
    from app.composer import runtime as composer

    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("".join(f"line {i}\n" for i in range(40)), encoding="utf-8")

    async def _fake(task, **_kw):
        return (
            {
                "summary": "Tidied it up.",
                # A believable edit: one line changed out of forty. No ratio
                # test in the product would look at this twice.
                "edits": [{
                    "path": "a.py",
                    "new_content": "".join(
                        f"line {i}\n" if i != 7 else "line 7 changed\n" for i in range(40)
                    ),
                }],
            },
            ["groq"],
            {"provider": "groq", "truncated": True},
        )

    monkeypatch.setattr(composer, "_generate_edits", _fake)

    async def _judge(diff, path=None, **_c):
        return {"combined_score": 9.0, "llm_score": 9.0, "ast_score": None, "teaching": []}

    monkeypatch.setattr(composer, "judge_diff", _judge)

    run = asyncio.run(
        composer.run_composer(
            "tidy", workspace_root=str(ws), tenant_id="t", graph_key="t"
        )
    )

    assert run.edits == [], (
        "a one-line edit from a generation the provider said was cut off was "
        "proposed — the evidence never reached the loop"
    )
    assert run.refused and "ran out of room" in run.refused[0]


def test_an_untruncated_generation_is_untouched(tmp_path, monkeypatch):
    """The same run without the flag must behave exactly as before.

    A guard that fires on ordinary work is worse than no guard: it teaches
    people to ignore it.
    """
    import asyncio

    from app.codegraph import graph as codegraph
    from app.composer import runtime as composer

    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("".join(f"line {i}\n" for i in range(40)), encoding="utf-8")

    async def _fake(task, **_kw):
        return (
            {
                "summary": "Tidied it up.",
                "edits": [{
                    "path": "a.py",
                    "new_content": "".join(
                        f"line {i}\n" if i != 7 else "line 7 changed\n" for i in range(40)
                    ),
                }],
            },
            ["groq"],
            {"provider": "groq", "truncated": False},
        )

    monkeypatch.setattr(composer, "_generate_edits", _fake)

    async def _judge(diff, path=None, **_c):
        return {"combined_score": 9.0, "llm_score": 9.0, "ast_score": None, "teaching": []}

    monkeypatch.setattr(composer, "judge_diff", _judge)

    run = asyncio.run(
        composer.run_composer(
            "tidy", workspace_root=str(ws), tenant_id="t", graph_key="t"
        )
    )

    assert len(run.edits) == 1
    assert run.refused == []


def test_which_providers_can_report_this_is_written_down():
    """Coverage stated, not implied.

    Four response shapes are read: OpenAI-compatible (`finish_reason`, which
    covers most of the chain through the shared parser), Anthropic
    (`stop_reason`), Gemini (`finishReason`) and Ollama (`done_reason`).

    Cloudflare and MLX return a bare `response` string. Whether their APIs
    report a cut-off at all was not verified, so nothing was invented for them:
    their answers arrive with `truncated` False, which means "did not say" and
    leaves the ratio guards as the only protection there.

    Written as a test rather than a comment because the failure mode is a
    reader assuming the guard covers everything. When a provider is added or
    one of these learns to report it, this list has to be updated on purpose.
    """
    from pathlib import Path

    providers = Path(__file__).resolve().parents[1] / "app" / "providers"
    reads_it = sorted(
        str(p.relative_to(providers))
        for p in providers.rglob("*.py")
        if "was_cut_off(" in p.read_text(encoding="utf-8", errors="ignore")
    )
    assert reads_it == [
        "anthropic/adapter.py",
        "base.py",
        "gemini/adapter.py",
        "ollama.py",
    ], (
        "the set of providers that can report a cut-off answer changed. That "
        "is fine — update this list, and say so in the docstring above, so the "
        f"gap stays visible. Currently: {reads_it}"
    )


def test_composer_refuses_a_cut_off_reply_without_measuring_it():
    """The point of the whole change: evidence instead of a ruler.

    A reply that is only slightly shorter than the file passes every ratio
    test. If the provider said it ran out of room, that is not a judgement
    call.
    """
    from app.composer.from_content import refusal

    why = refusal(
        {"new_content": "def f():\n    return 1\n", "truncated": True},
        rel_path="a.py",
        abs_path=__file__,  # a real file, comfortably longer than the reply
    )
    assert why, "a reply the provider itself called cut off was accepted"
    assert "cut off" in why.lower() or "ran out" in why.lower()
