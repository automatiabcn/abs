"""Sprint Q12 — Pin the new (judge-free) PROMISE.md evidence stack.

The v1.3 rewrite of `docs/ABS_HYBRID_TIER_PROMISE.md` replaced the
multi-judge consensus eval with three deterministic promises:
latency, cost, redundancy. These tests lock the contracts of:

  1. `scripts/eval/latency_benchmark.py` — schema + percentile math
  2. `scripts/eval/cost_calculator.py` — token × pricing arithmetic
  3. `scripts/eval/cascade_smoke.py` — runs end-to-end on stubs
  4. `docs/ABS_HYBRID_TIER_PROMISE.md` — v1.3 structure (sections
     present, retracted claim absent, legacy 'Quality bar' removed)

No live API calls. This is a pure-function + structural contract
suite so the doc + scripts can't drift apart silently.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest


REPO = pathlib.Path(__file__).resolve().parents[3]
LATENCY_SCRIPT = REPO / "scripts/eval/latency_benchmark.py"
COST_SCRIPT = REPO / "scripts/eval/cost_calculator.py"
CASCADE_SCRIPT = REPO / "scripts/eval/cascade_smoke.py"
PROMISE_DOC = REPO / "docs/ABS_HYBRID_TIER_PROMISE.md"
LATENCY_JSON = REPO / "artifacts/promise_verify/latency_benchmark.json"


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. latency_benchmark.py contract
# ---------------------------------------------------------------------------


def test_promise_v6_latency_aggregate_handles_empty_anthropic():
    """When ANTHROPIC_API_KEY is absent, every Anthropic sample is an
    error. aggregate() must surface `errors=N` and leave speedup as
    None — never invent a multiplier against zero successful samples."""
    mod = _load_module(LATENCY_SCRIPT, "latency_benchmark_t1")
    samples = [
        {
            "id": "x-1",
            "category": "code",
            "groq": {"latency_ms": 100.0, "input_tokens": 50, "output_tokens": 200},
            "anthropic": {"error": "anthropic_unavailable"},
        },
        {
            "id": "x-2",
            "category": "code",
            "groq": {"latency_ms": 200.0, "input_tokens": 60, "output_tokens": 240},
            "anthropic": {"error": "anthropic_unavailable"},
        },
    ]
    summary = mod.aggregate(samples)
    assert summary["n_prompts"] == 2
    assert summary["groq"]["n_ok"] == 2
    assert summary["groq"]["errors"] == 0
    assert summary["anthropic"]["n_ok"] == 0
    assert summary["anthropic"]["errors"] == 2
    assert summary["speedup"] is None, "no Anthropic data → no speedup"


def test_promise_v6_latency_percentile_math():
    """P50/mean on a known dataset — guards against off-by-one in the
    interpolation (pandas-compatible at N=100)."""
    mod = _load_module(LATENCY_SCRIPT, "latency_benchmark_t2")
    # Build a fake 5-sample run; P50 of [10,20,30,40,50] = 30.
    samples = [
        {
            "id": f"id-{i}",
            "category": "code",
            "groq": {"latency_ms": v, "input_tokens": 0, "output_tokens": 0},
            "anthropic": {"latency_ms": v * 5, "input_tokens": 0, "output_tokens": 0},
        }
        for i, v in enumerate([10.0, 20.0, 30.0, 40.0, 50.0])
    ]
    summary = mod.aggregate(samples)
    assert summary["groq"]["p50_ms"] == pytest.approx(30.0, abs=0.1)
    assert summary["groq"]["mean_ms"] == pytest.approx(30.0, abs=0.1)
    # Anthropic = Groq × 5 ⇒ speedup mean = 5.0
    assert summary["speedup"]["mean"] == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# 2. cost_calculator.py contract
# ---------------------------------------------------------------------------


def test_promise_v6_cost_pricing_table_and_math():
    """Cost arithmetic must match published rates exactly (Sonnet 4.5
    $3 input + $15 output per Mtok; Groq free)."""
    mod = _load_module(COST_SCRIPT, "cost_calculator_t1")
    assert mod.PRICING["groq"]["input_per_mtok_usd"] == 0.0
    assert mod.PRICING["groq"]["output_per_mtok_usd"] == 0.0
    assert mod.PRICING["anthropic"]["input_per_mtok_usd"] == 3.0
    assert mod.PRICING["anthropic"]["output_per_mtok_usd"] == 15.0
    # 1000 input + 1000 output @ Sonnet rates = 0.003 + 0.015 = 0.018
    assert mod.cost_for("anthropic", 1000, 1000) == pytest.approx(0.018, abs=1e-9)
    assert mod.cost_for("groq", 1_000_000, 1_000_000) == 0.0


def test_promise_v6_cost_ledger_flags_anthropic_floor_estimate():
    """When latency JSON has zero Anthropic tokens but non-zero Groq
    tokens, the ledger must mark `anthropic_estimated_from_groq=True`
    so the artifact never silently inflates the cost claim."""
    mod = _load_module(COST_SCRIPT, "cost_calculator_t2")
    fake_latency = {
        "summary": {
            "n_prompts": 10,
            "groq": {"total_input_tokens": 1500, "total_output_tokens": 5000},
            "anthropic": {"total_input_tokens": 0, "total_output_tokens": 0},
        }
    }
    ledger = mod.build_ledger(fake_latency, [1000])
    assert ledger["anthropic_estimated_from_groq"] is True
    # 150 in + 500 out per prompt × 1000 prompts × Sonnet pricing
    # = 150_000 * 3/1e6 + 500_000 * 15/1e6 = 0.45 + 7.5 = 7.95
    assert ledger["monthly_projection_usd"]["1000"]["anthropic_usd"] == pytest.approx(
        7.95, abs=0.01
    )
    assert ledger["monthly_projection_usd"]["1000"]["groq_usd"] == 0.0


# ---------------------------------------------------------------------------
# 3. cascade_smoke.py contract — runs end-to-end on stubs
# ---------------------------------------------------------------------------


def test_promise_v6_cascade_smoke_runs_green():
    """Run the cascade smoke as a subprocess; require 7/7 rounds.

    This is a contract smoke for the script itself, on top of the
    dedicated `test_cascade*.py` suites that cover the orchestrator
    semantics directly.
    """
    rc = subprocess.call(
        [sys.executable, str(CASCADE_SCRIPT)],
        cwd=str(REPO),
    )
    assert rc == 0, "cascade_smoke.py returned non-zero"
    art_json = REPO / "artifacts/promise_verify/cascade_smoke.json"
    assert art_json.exists()
    body = json.loads(art_json.read_text(encoding="utf-8"))
    rep = body["report"]
    assert rep["passed"] == rep["total"] == 7, rep
    # Six providers in the paid-first chain.
    assert len(rep["chain"]) == 6
    assert rep["chain"][0] == "anthropic"


# ---------------------------------------------------------------------------
# 4. PROMISE.md v1.3 structural contract
# ---------------------------------------------------------------------------


def test_promise_v6_doc_v13_structure():
    """The PROMISE.md must:
    - declare itself v1.3
    - contain the three new section headers
    - retain the 'What we do NOT claim' retraction paragraph
    - not contain the deleted 'Quality bar' header or
      '≥50 % win-rate' claim phrasing
    """
    text = PROMISE_DOC.read_text(encoding="utf-8")
    # Header
    assert "v1.3" in text.splitlines()[2], text.splitlines()[2]
    # New sections
    assert "## What we measure (and what we don't)" in text
    assert "## What we do NOT claim" in text
    assert "### 1. Latency" in text
    assert "### 2. Cost" in text
    assert "### 3. Redundancy" in text
    # Deleted section / retracted claim
    assert "## Quality bar" not in text, "old 'Quality bar' header must be removed"
    assert "≥50 % win-rate" not in text and "≥50% win-rate" not in text, (
        "retracted win-rate claim must not reappear"
    )
    # Pointers to the three new evidence files
    assert "latency_benchmark.md" in text
    assert "cost_ledger.md" in text
    assert "cascade_smoke.md" in text


def test_promise_v6_latency_artifact_exists_and_well_formed():
    """The R1 live run produced the latency JSON. CI must see it
    sit at the documented path with the documented schema."""
    assert LATENCY_JSON.exists(), (
        "Run `python scripts/eval/latency_benchmark.py` to regenerate. "
        "PROMISE.md v1.3 references this artifact path."
    )
    body = json.loads(LATENCY_JSON.read_text(encoding="utf-8"))
    assert body["mode"] in {"live", "live-no-anthropic", "offline"}
    summary = body["summary"]
    assert "groq" in summary and "anthropic" in summary
    assert "n_prompts" in summary
    # Speedup is None or has p50/p95/mean keys — never partially specified.
    sp = summary.get("speedup")
    if sp is not None:
        assert {"p50", "p95", "mean"} <= set(sp.keys())
