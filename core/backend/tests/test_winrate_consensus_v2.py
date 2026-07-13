"""Multi-judge consensus eval v2 — pure-function contract tests.

Covers R1–R4 of the bias-controlled win-rate harness:
  R1. judge_one() dispatches on provider= groq/anthropic/gemini/cohere
      and surfaces transport errors as VERDICT_ERROR (no silent TIE).
  R2. dataset has been expanded to 100 prompts with the
      objective-trait schema.
  R3. RateLimitError + exponential backoff retry behaves correctly,
      and AnthropicThrottle clamps Plus-tier bursts.
  R4. consensus() applies the 6/8 strong + 5/8 weak threshold and
      excludes ERROR verdicts from the denominator; Wilson 95 % CI
      narrows monotonically with N.

These are unit tests — no live provider calls are made. The live path
is exercised manually by `python scripts/eval/winrate_consensus.py`
when both keys are set in the operator's environment.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest


REPO = pathlib.Path(__file__).resolve().parents[3]
BASE_SCRIPT = REPO / "scripts/eval/multimodel_winrate.py"
CONSENSUS_SCRIPT = REPO / "scripts/eval/winrate_consensus.py"
DATASET = REPO / "core/backend/tests/fixtures/golden_eval_multimodel.json"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def base_mod():
    return _load("multimodel_winrate", BASE_SCRIPT)


@pytest.fixture(scope="module")
def consensus_mod(base_mod):
    # The consensus script does `import multimodel_winrate as base`
    # via sys.path; reuse the already-loaded base instance to keep
    # monkeypatching observable across both modules.
    import sys

    sys.modules["multimodel_winrate"] = base_mod
    return _load("winrate_consensus", CONSENSUS_SCRIPT)


# ─────────────────────────── R1: dispatch ────────────────────────────


def test_judge_one_dispatches_per_provider(consensus_mod, monkeypatch):
    """Every provider branch must route through its own call_* helper.

    The dispatch is the bias-control mechanism: if all 4 judges
    silently collapsed onto one helper we'd be back to single-judge
    bias. This test pins the routing so a future refactor can't
    regress it.
    """
    base = consensus_mod.base
    calls: list[tuple[str, str]] = []

    def fake(provider_name: str, ret: str):
        def _f(prompt, model, api_key):
            calls.append((provider_name, model))
            return ret

        return _f

    monkeypatch.setattr(base, "call_groq", fake("groq", "A"))
    monkeypatch.setattr(base, "call_claude", fake("anthropic", "B"))
    monkeypatch.setattr(base, "call_gemini", fake("gemini", "TIE"))
    monkeypatch.setattr(base, "call_cohere", fake("cohere", "A"))

    keys = {"groq": "g", "anthropic": "a", "gemini": "x", "cohere": "c"}

    assert (
        consensus_mod.judge_one(
            "task",
            ["t1"],
            "ans-a",
            "ans-b",
            provider="groq",
            model="llama-3.3-70b-versatile",
            keys=keys,
        )
        == "A"
    )
    assert (
        consensus_mod.judge_one(
            "task",
            ["t1"],
            "ans-a",
            "ans-b",
            provider="anthropic",
            model="claude-sonnet-4-5",
            keys=keys,
        )
        == "B"
    )
    assert (
        consensus_mod.judge_one(
            "task",
            ["t1"],
            "ans-a",
            "ans-b",
            provider="gemini",
            model="gemini-2.5-pro",
            keys=keys,
        )
        == "TIE"
    )
    assert (
        consensus_mod.judge_one(
            "task",
            ["t1"],
            "ans-a",
            "ans-b",
            provider="cohere",
            model="command-r-plus-08-2024",
            keys=keys,
        )
        == "A"
    )

    providers_called = [p for p, _ in calls]
    assert providers_called == ["groq", "anthropic", "gemini", "cohere"]


def test_judge_one_missing_key_returns_error_not_tie(consensus_mod):
    """If a judge's API key is unset we MUST surface 'ERROR' rather
    than fabricate a TIE. The aggregate then excludes that verdict."""
    keys = {"groq": "g", "anthropic": None, "gemini": None, "cohere": None}
    assert (
        consensus_mod.judge_one(
            "t",
            [],
            "x",
            "y",
            provider="anthropic",
            model="claude-sonnet-4-5",
            keys=keys,
        )
        == "ERROR"
    )
    assert (
        consensus_mod.judge_one(
            "t", [], "x", "y", provider="gemini", model="gemini-2.5-pro", keys=keys
        )
        == "ERROR"
    )
    assert (
        consensus_mod.judge_one(
            "t",
            [],
            "x",
            "y",
            provider="cohere",
            model="command-r-plus-08-2024",
            keys=keys,
        )
        == "ERROR"
    )


def test_judge_one_rate_limit_after_retry_returns_error(consensus_mod, monkeypatch):
    """RateLimitError that survives the retry wrapper must NOT be
    silently coerced to TIE — the verdict is 'ERROR' and the row's
    consensus excludes it."""
    base = consensus_mod.base

    def boom(*_a, **_kw):
        raise base.RateLimitError("groq", 429, 0.0, "rate limited")

    monkeypatch.setattr(base, "call_groq", boom)
    keys = {"groq": "g", "anthropic": "a", "gemini": "x", "cohere": "c"}
    out = consensus_mod.judge_one(
        "t", [], "x", "y", provider="groq", model="llama-3.3-70b-versatile", keys=keys
    )
    assert out == "ERROR"


# ───────────────────── R3: rate limit + throttle ────────────────────


def test_rate_limit_retry_eventually_succeeds(base_mod, monkeypatch):
    """Two 429s then 200 → wrapper returns the eventual payload."""
    attempts = {"n": 0}

    def fake_post(url, body, headers, timeout=60.0, *, provider="?"):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise base_mod.RateLimitError(provider, 429, 0.0, "throttled")
        return {"ok": True, "n": attempts["n"]}

    monkeypatch.setattr(base_mod, "_http_post_json", fake_post)
    monkeypatch.setattr(base_mod.time, "sleep", lambda _s: None)

    result = base_mod._post_with_retry(
        "u", {}, {}, provider="groq", base_sleep=0.01, max_sleep=0.02, max_retries=4
    )
    assert result == {"ok": True, "n": 3}
    assert attempts["n"] == 3


def test_rate_limit_retry_gives_up_after_max(base_mod, monkeypatch):
    """If the provider stays 429-stuck the wrapper re-raises rather
    than silently downgrading to a fake response."""

    def always_429(url, body, headers, timeout=60.0, *, provider="?"):
        raise base_mod.RateLimitError(provider, 429, 0.0, "stuck")

    monkeypatch.setattr(base_mod, "_http_post_json", always_429)
    monkeypatch.setattr(base_mod.time, "sleep", lambda _s: None)

    with pytest.raises(base_mod.RateLimitError):
        base_mod._post_with_retry(
            "u",
            {},
            {},
            provider="cohere",
            base_sleep=0.001,
            max_sleep=0.002,
            max_retries=2,
        )


def test_anthropic_throttle_blocks_at_cap(base_mod, monkeypatch):
    """30 calls in <15min must trigger a sleep before the 31st call.

    We capture the requested sleep value rather than actually sleeping
    so the test stays under a millisecond.
    """
    sleeps: list[float] = []
    monkeypatch.setattr(base_mod.time, "sleep", lambda s: sleeps.append(s))
    # Pin "now" so 30 timestamps fit cleanly inside the window.
    fake_now = [1_000_000.0]
    monkeypatch.setattr(base_mod.time, "time", lambda: fake_now[0])
    th = base_mod.AnthropicThrottle()
    for _ in range(th.MAX_CALLS):
        th.acquire()
    assert sleeps == []  # 30 calls at the same instant — no throttle yet
    # 31st call within the same window must request a sleep
    th.acquire()
    assert sleeps, "AnthropicThrottle did not sleep after exceeding cap"
    assert sleeps[0] > 0


# ─────────────────────── R4: consensus + Wilson ─────────────────────


def test_consensus_thresholds(consensus_mod):
    c = consensus_mod.consensus
    assert c(["A"] * 6 + ["B"] * 2) == ("gpt_oss_wins", "confident_strong")
    assert c(["A"] * 5 + ["B"] * 3) == ("gpt_oss_wins", "confident_weak")
    assert c(["A"] * 4 + ["B"] * 4) == ("uncertain", "uncertain")
    assert c(["B"] * 7 + ["A"]) == ("claude_wins", "confident_strong")
    # Errors are excluded from the denominator entirely.
    assert c(["A", "A", "A", "ERROR", "ERROR", "ERROR", "ERROR", "ERROR"]) == (
        "uncertain",
        "uncertain",
    )
    # All-error → no_data, never a fabricated TIE.
    assert c(["ERROR"] * 8) == ("uncertain", "no_data")


def test_wilson_ci_narrows_with_n(consensus_mod):
    low_n_low, low_n_high = consensus_mod._wilson_ci(5, 10)
    high_n_low, high_n_high = consensus_mod._wilson_ci(50, 100)
    assert (low_n_high - low_n_low) > (high_n_high - high_n_low)
    # Empty CI is degenerate but well-defined.
    assert consensus_mod._wilson_ci(0, 0) == (0.0, 0.0)


# ─────────────────────────── R2: dataset ─────────────────────────────


def test_dataset_v2_has_100_rows_balanced(consensus_mod):
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(rows) == 100, f"expected 100 rows, got {len(rows)}"
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    assert counts == {"code": 25, "analysis": 25, "translation": 25, "writing": 25}, (
        counts
    )
    seen_ids: set[str] = set()
    for r in rows:
        assert {"id", "category", "task", "expected_traits"} <= set(r.keys())
        assert r["id"] not in seen_ids, f"duplicate id {r['id']}"
        seen_ids.add(r["id"])
        assert r["task"].strip(), f"empty task in {r['id']}"
        assert isinstance(r["expected_traits"], list)
        assert len(r["expected_traits"]) >= 3, f"{r['id']} has too few traits"
        for t in r["expected_traits"]:
            assert isinstance(t, str) and t.strip(), f"{r['id']} bad trait {t!r}"
