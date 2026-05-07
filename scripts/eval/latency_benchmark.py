"""Sprint Q12 — Latency benchmark (judge-free, rate-limit-safe).

Measures wall-clock latency for two providers on the same 100-prompt
golden eval dataset. NO LLM-as-judge. NO Cohere/Gemini calls (those are
in 24h cooldown after the 2026-05-06 rate-limit storm).

Why this replaces the consensus eval:
  4-judge × position-swap consensus produced 58 pp cross-judge variance
  on the very first prompt — pure noise. Customers feel three concrete
  things: latency, cost, redundancy. This script ships #1.

Output: `artifacts/promise_verify/latency_benchmark.{md,json}`.

Honest gating:
  - GROQ_API_KEY missing      → exit 2, no artifact rewrite.
  - ANTHROPIC_API_KEY missing → Anthropic rows recorded as
    `anthropic_unavailable`; speedup left null. The artifact still
    captures the Groq side so the customer sees its absolute numbers.

Usage:
  python scripts/eval/latency_benchmark.py            # N=100 full run
  python scripts/eval/latency_benchmark.py --limit 5  # smoke
  python scripts/eval/latency_benchmark.py --offline  # contract-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import pathlib
import statistics
import sys
import time
from typing import Any

# Re-use the wire-level helpers + Anthropic Plus throttle that the legacy
# winrate harness already proved against the live providers, instead of
# duplicating httpx plumbing.
ROOT = pathlib.Path(__file__).resolve().parents[2]
WINRATE_SCRIPT = ROOT / "scripts/eval/multimodel_winrate.py"
DATASET = ROOT / "core/backend/tests/fixtures/golden_eval_multimodel.json"
ARTIFACT_MD = ROOT / "artifacts/promise_verify/latency_benchmark.md"
ARTIFACT_JSON = ROOT / "artifacts/promise_verify/latency_benchmark.json"


def _load_winrate_mod():
    spec = importlib.util.spec_from_file_location(
        "multimodel_winrate", WINRATE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. Pandas-compatible for N=100."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _summarise(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute P50/P95/mean over the `latency_ms` field of each sample.

    Errored samples (missing `latency_ms`) are counted in `errors` and
    excluded from the percentile math so a single 429 doesn't poison
    the headline numbers.
    """
    ok = [s["latency_ms"] for s in samples if "latency_ms" in s]
    err = sum(1 for s in samples if "error" in s)
    if not ok:
        return {
            "n_ok": 0,
            "errors": err,
            "p50_ms": None,
            "p95_ms": None,
            "mean_ms": None,
            "stdev_ms": None,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
    in_tok = sum(s.get("input_tokens", 0) for s in samples)
    out_tok = sum(s.get("output_tokens", 0) for s in samples)
    return {
        "n_ok": len(ok),
        "errors": err,
        "p50_ms": round(_percentile(ok, 50), 1),
        "p95_ms": round(_percentile(ok, 95), 1),
        "mean_ms": round(statistics.mean(ok), 1),
        "stdev_ms": round(statistics.stdev(ok), 1) if len(ok) > 1 else 0.0,
        "total_input_tokens": in_tok,
        "total_output_tokens": out_tok,
    }


def _speedup(anth: dict[str, Any], groq: dict[str, Any]) -> dict[str, Any] | None:
    """Anthropic / Groq ratio per metric. None when either side has no
    successful samples — we never invent a speedup against an empty
    Anthropic sample set."""
    if not (anth["n_ok"] and groq["n_ok"]):
        return None
    return {
        "p50": round(anth["p50_ms"] / groq["p50_ms"], 2) if groq["p50_ms"] else None,
        "p95": round(anth["p95_ms"] / groq["p95_ms"], 2) if groq["p95_ms"] else None,
        "mean": round(anth["mean_ms"] / groq["mean_ms"], 2) if groq["mean_ms"] else None,
    }


def call_groq_timed(mod, task: str, model: str, key: str) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": task}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    payload = mod._post_with_retry(
        mod.GROQ_BASE, body, headers, provider="groq",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    usage = payload.get("usage", {}) or {}
    return {
        "latency_ms": elapsed_ms,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def call_anthropic_timed(mod, task: str, model: str, key: str) -> dict[str, Any]:
    body = {
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": task}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    mod._anthropic_throttle.acquire()
    t0 = time.perf_counter()
    payload = mod._post_with_retry(
        mod.ANTHROPIC_BASE, body, headers, provider="anthropic",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    usage = payload.get("usage", {}) or {}
    return {
        "latency_ms": elapsed_ms,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def run_row(mod, row: dict[str, Any], *, groq_key: str | None,
            anth_key: str | None, groq_model: str,
            anth_model: str) -> dict[str, Any]:
    task = row["task"]
    out: dict[str, Any] = {"id": row["id"], "category": row["category"]}
    # Groq side
    if groq_key:
        try:
            g = call_groq_timed(mod, task, groq_model, groq_key)
            out["groq"] = g
        except Exception as exc:  # noqa: BLE001 — record every failure
            out["groq"] = {"error": f"groq_failed: {exc}"}
    else:
        out["groq"] = {"error": "groq_unavailable"}
    # Anthropic side — gated on key, skipped silently when absent.
    if anth_key:
        try:
            a = call_anthropic_timed(mod, task, anth_model, anth_key)
            out["anthropic"] = a
        except Exception as exc:  # noqa: BLE001
            out["anthropic"] = {"error": f"anthropic_failed: {exc}"}
    else:
        out["anthropic"] = {"error": "anthropic_unavailable"}
    return out


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure function — exposed for tests."""
    groq_rows = [s["groq"] for s in samples]
    anth_rows = [s["anthropic"] for s in samples]
    groq = _summarise(groq_rows)
    anth = _summarise(anth_rows)
    return {
        "n_prompts": len(samples),
        "groq": groq,
        "anthropic": anth,
        "speedup": _speedup(anth, groq),
    }


def render_markdown(*, summary: dict[str, Any], groq_model: str,
                    anth_model: str, finished_at: str,
                    duration_s: float, mode: str) -> str:
    lines: list[str] = []
    lines.append("# Latency benchmark — Groq vs Anthropic\n\n")
    lines.append(
        f"> Generated: {finished_at} · mode: `{mode}` · duration: "
        f"{duration_s:.1f}s\n"
    )
    lines.append(
        f"> Dataset: `core/backend/tests/fixtures/golden_eval_multimodel.json`"
        f" ({summary['n_prompts']} prompts)\n"
    )
    lines.append(f"> Groq model: `{groq_model}`\n")
    lines.append(f"> Anthropic model: `{anth_model}`\n\n")
    lines.append("## Wall-clock latency\n\n")
    lines.append("| Provider | n_ok | errors | P50 (ms) | P95 (ms) | mean (ms) | stdev (ms) |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for label, key in (("Groq GPT-OSS-120B", "groq"),
                       ("Anthropic Sonnet 4.5", "anthropic")):
        s = summary[key]
        lines.append(
            f"| {label} | {s['n_ok']} | {s['errors']} | "
            f"{s['p50_ms']} | {s['p95_ms']} | {s['mean_ms']} | "
            f"{s['stdev_ms']} |\n"
        )
    lines.append("\n## Speedup (Anthropic / Groq)\n\n")
    sp = summary["speedup"]
    if sp is None:
        lines.append(
            "_Speedup unmeasured — one provider returned zero successful "
            "samples (typical when `ANTHROPIC_API_KEY` is not set)._\n"
        )
    else:
        lines.append("| Metric | Multiplier |\n|---|---|\n")
        lines.append(f"| P50 | {sp['p50']}× |\n")
        lines.append(f"| P95 | {sp['p95']}× |\n")
        lines.append(f"| mean | {sp['mean']}× |\n")
    lines.append("\n## Token usage (sum across all prompts)\n\n")
    lines.append("| Provider | Input tokens | Output tokens |\n|---|---|---|\n")
    for label, key in (("Groq", "groq"), ("Anthropic", "anthropic")):
        s = summary[key]
        lines.append(
            f"| {label} | {s['total_input_tokens']} | "
            f"{s['total_output_tokens']} |\n"
        )
    lines.append("\n## Notes\n\n")
    lines.append(
        "- Wall-clock timing uses `time.perf_counter()` around each HTTP "
        "POST, including TLS handshake — that is the customer-felt latency.\n"
    )
    lines.append(
        "- `AnthropicThrottle` (≤30 calls / 15-min) is honoured to keep the "
        "Plus tier within budget during the run.\n"
    )
    lines.append(
        "- No LLM-as-judge is invoked; this script makes no claim about "
        "output quality. See `cost_ledger.md` and `cascade_smoke.md` for "
        "the other two empirical promises.\n"
    )
    lines.append("\n## Reproduce\n\n```bash\n")
    lines.append("export GROQ_API_KEY=...\n")
    lines.append("export ANTHROPIC_API_KEY=...    # optional, opt-in only\n")
    lines.append("python scripts/eval/latency_benchmark.py\n```\n")
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Run only the first N rows.")
    parser.add_argument("--offline", action="store_true",
                        help="Contract-only run; skip live calls.")
    parser.add_argument("--groq-model", default="openai/gpt-oss-120b")
    parser.add_argument("--anthropic-model",
                        default="claude-sonnet-4-5-20250929")
    args = parser.parse_args()

    if not DATASET.exists():
        print(f"dataset missing: {DATASET}", file=sys.stderr)
        return 2
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]

    started_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()

    mode: str
    samples: list[dict[str, Any]]
    if args.offline:
        samples = [
            {
                "id": r["id"],
                "category": r["category"],
                "groq": {"error": "offline_mode"},
                "anthropic": {"error": "offline_mode"},
            }
            for r in rows
        ]
        mode = "offline"
    else:
        groq_key = os.getenv("GROQ_API_KEY") or None
        anth_key = os.getenv("ANTHROPIC_API_KEY") or None
        if not groq_key:
            print("GROQ_API_KEY missing; refusing to run.", file=sys.stderr)
            return 2
        mod = _load_winrate_mod()
        samples = []
        for row in rows:
            s = run_row(mod, row, groq_key=groq_key, anth_key=anth_key,
                        groq_model=args.groq_model,
                        anth_model=args.anthropic_model)
            samples.append(s)
            g = s["groq"].get("latency_ms")
            a = s["anthropic"].get("latency_ms")
            print(f"[{s['id']}] groq={g} anthropic={a}")
        mode = "live" if anth_key else "live-no-anthropic"

    duration_s = time.time() - t0
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary = aggregate(samples)

    ARTIFACT_MD.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_MD.write_text(
        render_markdown(
            summary=summary,
            groq_model=args.groq_model,
            anth_model=args.anthropic_model,
            finished_at=finished_at,
            duration_s=duration_s,
            mode=mode,
        ),
        encoding="utf-8",
    )
    ARTIFACT_JSON.write_text(
        json.dumps(
            {
                "mode": mode,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_s": round(duration_s, 2),
                "groq_model": args.groq_model,
                "anthropic_model": args.anthropic_model,
                "summary": summary,
                "samples": samples,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nartifact: {ARTIFACT_MD}")
    print(f"json:     {ARTIFACT_JSON}")
    g = summary["groq"]
    a = summary["anthropic"]
    print(f"groq:      P50={g['p50_ms']}ms  P95={g['p95_ms']}ms  mean={g['mean_ms']}ms  errors={g['errors']}")
    print(f"anthropic: P50={a['p50_ms']}ms  P95={a['p95_ms']}ms  mean={a['mean_ms']}ms  errors={a['errors']}")
    if summary["speedup"]:
        sp = summary["speedup"]
        print(f"speedup:   P50={sp['p50']}×  P95={sp['p95']}×  mean={sp['mean']}×")
    return 0


if __name__ == "__main__":
    sys.exit(main())
