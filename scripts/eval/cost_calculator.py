# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint Q12 — Cost ledger (token × pricing, zero API calls).

Reads `artifacts/promise_verify/latency_benchmark.json` and prices the
recorded token usage against published pricing. No LLM call. No
network. Pure arithmetic so the artifact is reproducible without any
key.

Pricing (per million tokens, USD, 2026-05-07):
  - Groq GPT-OSS-120B: $0 input / $0 output (free tier)
  - Anthropic Claude Sonnet 4.5: $3 input / $15 output

Output: `artifacts/promise_verify/cost_ledger.{md,json}`.

The script also projects a monthly bill at 1000 prompts (a typical
solo-founder workload) and at 10 000 (small-team). When latency
benchmark didn't measure Anthropic (no key), the calculator estimates
Anthropic-side cost from the *Groq token counts* — a deliberate floor:
real Sonnet 4.5 typically returns longer output, so this projection
is on the optimistic side and the ledger says so.

Usage:
  python scripts/eval/cost_calculator.py
  python scripts/eval/cost_calculator.py --monthly 1000 --monthly 10000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
LATENCY_JSON = ROOT / "artifacts/promise_verify/latency_benchmark.json"
ARTIFACT_MD = ROOT / "artifacts/promise_verify/cost_ledger.md"
ARTIFACT_JSON = ROOT / "artifacts/promise_verify/cost_ledger.json"


# Pricing rates ($/Mtok). Single source of truth — bumping these is
# the only knob a future migration needs to turn.
PRICING = {
    "groq": {
        "model": "openai/gpt-oss-120b",
        "input_per_mtok_usd": 0.0,
        "output_per_mtok_usd": 0.0,
    },
    "anthropic": {
        "model": "claude-sonnet-4-5-20250929",
        "input_per_mtok_usd": 3.0,
        "output_per_mtok_usd": 15.0,
    },
}


def cost_for(provider: str, in_tok: int, out_tok: int) -> float:
    """Compute USD cost for a single (input, output) token pair."""
    p = PRICING[provider]
    return (
        in_tok * p["input_per_mtok_usd"] / 1_000_000.0
        + out_tok * p["output_per_mtok_usd"] / 1_000_000.0
    )


def per_prompt_average(in_tok: int, out_tok: int, n_prompts: int) -> tuple[float, float]:
    """Mean (input, output) tokens per prompt — guards N=0."""
    if n_prompts <= 0:
        return 0.0, 0.0
    return in_tok / n_prompts, out_tok / n_prompts


def project(provider: str, mean_in: float, mean_out: float,
            n_monthly: int) -> float:
    """Monthly USD spend projection for `n_monthly` prompts at the
    benchmark's per-prompt token average."""
    return cost_for(provider, int(mean_in * n_monthly),
                    int(mean_out * n_monthly))


def build_ledger(latency: dict[str, Any], monthly_runs: list[int]) -> dict[str, Any]:
    """Pure function — exposed for tests."""
    summary = latency.get("summary", {})
    n_prompts = summary.get("n_prompts", 0)
    groq = summary.get("groq", {}) or {}
    anth = summary.get("anthropic", {}) or {}

    g_in = int(groq.get("total_input_tokens", 0) or 0)
    g_out = int(groq.get("total_output_tokens", 0) or 0)
    a_in = int(anth.get("total_input_tokens", 0) or 0)
    a_out = int(anth.get("total_output_tokens", 0) or 0)

    g_mean_in, g_mean_out = per_prompt_average(g_in, g_out, n_prompts)
    a_mean_in, a_mean_out = per_prompt_average(a_in, a_out, n_prompts)

    # If Anthropic side wasn't measured (no key), fall back to Groq's
    # token counts as a *floor* projection. We mark this fallback
    # explicitly so the artifact never silently inflates or deflates.
    anthropic_estimated_from_groq = (a_in == 0 and a_out == 0 and g_in > 0)
    proj_in = a_mean_in if not anthropic_estimated_from_groq else g_mean_in
    proj_out = a_mean_out if not anthropic_estimated_from_groq else g_mean_out

    monthly: dict[str, dict[str, float]] = {}
    for n in monthly_runs:
        monthly[str(n)] = {
            "groq_usd": round(project("groq", g_mean_in, g_mean_out, n), 4),
            "anthropic_usd": round(project("anthropic", proj_in, proj_out, n), 4),
        }

    cost_per_prompt = {
        "groq_usd": round(cost_for("groq", int(g_mean_in), int(g_mean_out)), 6),
        "anthropic_usd": round(cost_for(
            "anthropic", int(proj_in), int(proj_out)
        ), 6),
    }

    return {
        "n_prompts": n_prompts,
        "groq_total_tokens": {"input": g_in, "output": g_out},
        "anthropic_total_tokens": {"input": a_in, "output": a_out},
        "anthropic_estimated_from_groq": anthropic_estimated_from_groq,
        "per_prompt_avg_tokens": {
            "groq": {"input": round(g_mean_in, 1),
                     "output": round(g_mean_out, 1)},
            "anthropic": {"input": round(proj_in, 1),
                          "output": round(proj_out, 1)},
        },
        "cost_per_prompt": cost_per_prompt,
        "monthly_projection_usd": monthly,
        "pricing": PRICING,
    }


def render_markdown(ledger: dict[str, Any], *, latency_meta: dict[str, Any],
                    finished_at: str) -> str:
    lines: list[str] = []
    lines.append("# Cost ledger — Groq vs Anthropic\n\n")
    lines.append(
        f"> Generated: {finished_at} · derived from "
        "`artifacts/promise_verify/latency_benchmark.json`\n"
    )
    lines.append(
        f"> Latency run mode: `{latency_meta.get('mode', '?')}` · "
        f"N={ledger['n_prompts']} prompts\n"
    )
    if ledger["anthropic_estimated_from_groq"]:
        lines.append(
            "> ⚠️ Anthropic side did not run live in the latency "
            "benchmark; per-prompt cost is projected from **Groq token "
            "counts** as a floor estimate. Real Sonnet 4.5 outputs are "
            "typically longer, so a live re-run will likely raise these "
            "numbers, not lower them.\n"
        )
    lines.append("\n## Pricing (per million tokens)\n\n")
    lines.append("| Provider | Model | Input $/Mtok | Output $/Mtok |\n")
    lines.append("|---|---|---|---|\n")
    for prov, p in PRICING.items():
        lines.append(
            f"| {prov} | `{p['model']}` | "
            f"${p['input_per_mtok_usd']:.2f} | "
            f"${p['output_per_mtok_usd']:.2f} |\n"
        )

    lines.append("\n## Per-prompt cost (mean across the run)\n\n")
    lines.append("| Provider | Mean input tokens | Mean output tokens | Cost / prompt |\n")
    lines.append("|---|---|---|---|\n")
    pp = ledger["per_prompt_avg_tokens"]
    cpp = ledger["cost_per_prompt"]
    lines.append(
        f"| Groq | {pp['groq']['input']} | {pp['groq']['output']} | "
        f"${cpp['groq_usd']:.6f} |\n"
    )
    lines.append(
        f"| Anthropic | {pp['anthropic']['input']} | "
        f"{pp['anthropic']['output']} | ${cpp['anthropic_usd']:.6f} |\n"
    )

    lines.append("\n## Monthly projection (USD)\n\n")
    lines.append("| Workload | Groq monthly | Anthropic monthly |\n")
    lines.append("|---|---|---|\n")
    for n_str, costs in ledger["monthly_projection_usd"].items():
        lines.append(
            f"| {int(n_str):,} prompts/mo | "
            f"${costs['groq_usd']:.2f} | ${costs['anthropic_usd']:.2f} |\n"
        )

    plus_budget = 20.0
    anth_1k = ledger["monthly_projection_usd"].get("1000", {}).get("anthropic_usd")
    if anth_1k is not None:
        if anth_1k <= plus_budget:
            verdict = (
                f"At 1 000 prompts / month, Anthropic spend (${anth_1k:.2f}) "
                f"stays inside the $20 Claude Plus budget — quota_monitor "
                "(95 % hard block) keeps it that way at higher workloads."
            )
        else:
            verdict = (
                f"At 1 000 prompts / month, Anthropic spend (${anth_1k:.2f}) "
                f"already exceeds the $20 Claude Plus budget. quota_monitor "
                "fires at 80 % and hard-blocks at 95 %, so over-budget calls "
                "fall through to Groq."
            )
        lines.append(f"\n{verdict}\n")

    lines.append("\n## What this ledger does NOT include\n\n")
    lines.append(
        "- Cohere embedding/rerank free-tier (separate quota, not LLM tokens)\n"
    )
    lines.append(
        "- Gemini 2.5 Flash / Pro multimodal free-tier (out of scope here; "
        "cascade evidence in `cascade_smoke.md`)\n"
    )
    lines.append(
        "- Cloudflare Workers AI free allotment\n"
    )
    lines.append(
        "- Local Ollama models (sunk cost, $0 marginal)\n"
    )

    lines.append("\n## Reproduce\n\n```bash\n")
    lines.append("python scripts/eval/cost_calculator.py\n```\n")
    lines.append(
        "\nNo network call. Re-runs are idempotent for a fixed "
        "`latency_benchmark.json`.\n"
    )
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--monthly", type=int, action="append",
        help="Monthly prompt count to project (repeatable). "
             "Defaults: 1000, 10000.",
    )
    parser.add_argument(
        "--latency-json", default=str(LATENCY_JSON),
        help="Path to the latency benchmark JSON sidecar.",
    )
    args = parser.parse_args()

    monthly = args.monthly or [1000, 10000]
    latency_path = pathlib.Path(args.latency_json)
    if not latency_path.exists():
        print(f"latency benchmark missing: {latency_path}", file=sys.stderr)
        print("Run `python scripts/eval/latency_benchmark.py` first.",
              file=sys.stderr)
        return 2

    latency = json.loads(latency_path.read_text(encoding="utf-8"))
    ledger = build_ledger(latency, monthly)
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    ARTIFACT_MD.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_MD.write_text(
        render_markdown(
            ledger,
            latency_meta={"mode": latency.get("mode", "?")},
            finished_at=finished_at,
        ),
        encoding="utf-8",
    )
    ARTIFACT_JSON.write_text(
        json.dumps(
            {
                "generated_at": finished_at,
                "source_latency_json": str(latency_path),
                "ledger": ledger,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"artifact: {ARTIFACT_MD}")
    print(f"json:     {ARTIFACT_JSON}")
    cpp = ledger["cost_per_prompt"]
    print(f"cost/prompt:  groq=${cpp['groq_usd']:.6f}  "
          f"anthropic=${cpp['anthropic_usd']:.6f}")
    for n_str, costs in ledger["monthly_projection_usd"].items():
        print(
            f"monthly @ {int(n_str):,} prompts: "
            f"groq=${costs['groq_usd']:.2f}  "
            f"anthropic=${costs['anthropic_usd']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
