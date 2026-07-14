# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Multi-judge consensus eval — bias-controlled win rate (v2).

Founder directive (2026-05-06): single-judge methodology biased
(Llama 80%, Sonnet 22% same dataset). v2 pipeline 4 judges × position
swap = 8 verdicts per prompt:

    Per prompt:
      - Run model A (GPT-OSS-120B)
      - Run model B (Claude — Sonnet/Opus)
      - 8 judge calls = 4 judges × {AB, BA}:
          1. Judge=Llama         (groq/llama-3.3-70b-versatile)
          2. Judge=Sonnet        (anthropic/claude-sonnet-4-5)
          3. Judge=Gemini Pro    (gemini/gemini-2.5-pro)
          4. Judge=Cohere R+     (cohere/command-r-plus-08-2024)

    Consensus rules (8 verdicts → bucket):
      - >=6/8 same letter (A or B)  → confident_strong
      - 5/8 same letter             → confident_weak
      - <=4/8 dominant              → uncertain
      - Errors are NEVER silently coerced to TIE; failed judge calls
        return verdict="ERROR" and are excluded from the per-prompt
        consensus *and* aggregate counts.

Output: artifacts/promise_verify/winrate_consensus_v2.md + JSON sidecar
with per-judge breakdown, per-judge position-swap rate, pairwise
inter-judge agreement, and Wilson 95 % confidence interval on the
confident win-rate.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
from collections import Counter
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "core/backend/tests/fixtures/golden_eval_multimodel.json"
ARTIFACT = ROOT / "artifacts/promise_verify/winrate_consensus_v2.md"
RESULTS_JSON = ROOT / "artifacts/promise_verify/winrate_consensus_v2.json"

sys.path.insert(0, str(ROOT / "scripts/eval"))
import multimodel_winrate as base  # noqa: E402  (path setup needed first)


VERDICT_ERROR = "ERROR"


def _invert(letter: str) -> str:
    if letter == "A":
        return "B"
    if letter == "B":
        return "A"
    if letter == "TIE":
        return "TIE"
    return VERDICT_ERROR


def judge_one(task: str, traits: list[str], a: str, b: str,
              provider: str, model: str,
              keys: dict[str, str | None]) -> str:
    """Returns 'A' | 'B' | 'TIE' | 'ERROR'.

    `keys` is a dict with 'groq', 'anthropic', 'gemini', 'cohere'
    entries (any may be None — callers exclude judges whose key is
    missing). Raises nothing — transport failures map to 'ERROR'.
    """
    prompt = base.JUDGE_PROMPT.format(
        task=task, traits="; ".join(traits),
        a=a[:4000], b=b[:4000],
    )
    try:
        if provider == "anthropic":
            key = keys.get("anthropic")
            if not key:
                return VERDICT_ERROR
            raw = base.call_claude(prompt, model=model, api_key=key)
        elif provider == "gemini":
            key = keys.get("gemini")
            if not key:
                return VERDICT_ERROR
            raw = base.call_gemini(prompt, model=model, api_key=key)
        elif provider == "cohere":
            key = keys.get("cohere")
            if not key:
                return VERDICT_ERROR
            raw = base.call_cohere(prompt, model=model, api_key=key)
        else:  # groq + anything else falls back to groq path
            key = keys.get("groq")
            if not key:
                return VERDICT_ERROR
            raw = base.call_groq(prompt, model=model, api_key=key)
    except base.RateLimitError:
        # Even after exponential backoff the provider is hard-rate-limited.
        # Surface explicitly rather than masking as TIE.
        return VERDICT_ERROR
    except Exception:
        return VERDICT_ERROR
    upper = (raw or "").strip().upper()
    if upper.startswith("A"):
        return "A"
    if upper.startswith("B"):
        return "B"
    if "TIE" in upper:
        return "TIE"
    return VERDICT_ERROR


def consensus(verdicts: list[str]) -> tuple[str, str]:
    """N verdict (errors excluded) → (final, confidence).

    final ∈ {gpt_oss_wins, claude_wins, tie, uncertain}
    confidence ∈ {confident_strong, confident_weak, uncertain, no_data}

    Rule, with N = non-error count:
      - majority>=ceil(N*0.75) and N>=4  → confident_strong
      - majority>=ceil(N*0.625) and N>=4 → confident_weak  (e.g. 5/8)
      - else                              → uncertain
    """
    clean = [v for v in verdicts if v != VERDICT_ERROR]
    n = len(clean)
    if n == 0:
        return "uncertain", "no_data"
    cnt = Counter(clean)
    letter, top = cnt.most_common(1)[0]
    strong_thr = math.ceil(n * 0.75)
    weak_thr = math.ceil(n * 0.625)
    if top >= strong_thr and n >= 4:
        conf = "confident_strong"
    elif top >= weak_thr and n >= 4:
        conf = "confident_weak"
    else:
        return "uncertain", "uncertain"
    if letter == "A":
        return "gpt_oss_wins", conf
    if letter == "B":
        return "claude_wins", conf
    return "tie", conf


def run_one(row: dict, *, gpt_oss_model: str, claude_model: str,
            judge_models: list[tuple[str, str]],
            keys: dict[str, str | None]) -> dict:
    out: dict[str, Any] = {
        "id": row["id"],
        "category": row.get("category", "?"),
        "verdicts": [],
        "consensus": "uncertain",
        "confidence": "no_data",
        "error": "",
    }
    task = row.get("task") or row.get("prompt", "")
    groq_key = keys.get("groq")
    claude_key = keys.get("anthropic")
    if not groq_key:
        out["error"] = "groq_key_missing"
        return out
    if not claude_key:
        out["error"] = "claude_key_missing"
        return out
    try:
        gpt_oss_resp = base.call_groq(task, gpt_oss_model, groq_key)
    except Exception as exc:
        out["error"] = f"gpt_oss_call_failed: {exc}"
        return out
    try:
        claude_resp = base.call_claude(task, claude_model, claude_key)
    except Exception as exc:
        out["error"] = f"claude_call_failed: {exc}"
        return out

    traits = row.get("expected_traits") or row.get("traits", [])
    verdict_letters: list[str] = []

    for judge_provider, judge_model in judge_models:
        v_ab = judge_one(task, traits, gpt_oss_resp, claude_resp,
                         judge_provider, judge_model, keys)
        v_ba = judge_one(task, traits, claude_resp, gpt_oss_resp,
                         judge_provider, judge_model, keys)
        v_ba_inv = _invert(v_ba)
        # Position-swap consistency only meaningful when both verdicts
        # are non-error AND non-TIE (TIE↔TIE swap is trivially consistent).
        consistent = (
            v_ab != VERDICT_ERROR
            and v_ba_inv != VERDICT_ERROR
            and v_ab == v_ba_inv
        )
        verdict_letters.extend([v_ab, v_ba_inv])
        out["verdicts"].append({
            "judge": f"{judge_provider}/{judge_model}",
            "ab": v_ab,
            "ba_inverted": v_ba_inv,
            "consistent": consistent,
            "errors": int(v_ab == VERDICT_ERROR) + int(v_ba == VERDICT_ERROR),
        })

    final, conf = consensus(verdict_letters)
    out["consensus"] = final
    out["confidence"] = conf
    out["raw_verdicts"] = verdict_letters
    return out


def _wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI for binomial proportion. Returns (low, high) in [0,1]."""
    if total == 0:
        return (0.0, 0.0)
    p_hat = wins / total
    denom = 1 + z * z / total
    centre = (p_hat + z * z / (2 * total)) / denom
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / total
                            + z * z / (4 * total * total))) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _per_judge_breakdown(results: list[dict],
                         judge_labels: list[str]) -> dict[str, dict]:
    """Per-judge win-rate + position-swap mismatch %.

    Win-rate is computed over non-error verdicts on the AB pass only
    (position bias is reported separately so it is not double-counted).
    """
    out: dict[str, dict] = {}
    for label in judge_labels:
        ab_letters: list[str] = []
        swap_total = 0
        swap_consistent = 0
        for r in results:
            for v in r.get("verdicts", []):
                if v["judge"] != label:
                    continue
                if v["ab"] != VERDICT_ERROR:
                    ab_letters.append(v["ab"])
                if v["ab"] != VERDICT_ERROR and v["ba_inverted"] != VERDICT_ERROR:
                    swap_total += 1
                    if v["consistent"]:
                        swap_consistent += 1
        n = len(ab_letters)
        a_wins = sum(1 for x in ab_letters if x == "A")
        b_wins = sum(1 for x in ab_letters if x == "B")
        ties = sum(1 for x in ab_letters if x == "TIE")
        win_pct = (a_wins / n * 100) if n else 0.0
        bias_pct = ((swap_total - swap_consistent) / swap_total * 100) if swap_total else 0.0
        out[label] = {
            "n": n,
            "a_wins": a_wins,
            "b_wins": b_wins,
            "ties": ties,
            "gpt_oss_win_pct_ab": round(win_pct, 1),
            "position_bias_pct": round(bias_pct, 1),
            "swap_pairs": swap_total,
        }
    return out


def _pairwise_agreement(results: list[dict],
                        judge_labels: list[str]) -> dict[str, float]:
    """Pairwise agreement on AB-pass verdicts (TIE counts as its own class).

    Returns {"judge_a||judge_b": agreement_pct}. Only rows where both
    judges produced non-error verdicts are counted.
    """
    out: dict[str, float] = {}
    for i, ja in enumerate(judge_labels):
        for jb in judge_labels[i + 1:]:
            agree = 0
            total = 0
            for r in results:
                v_a = next((v for v in r.get("verdicts", [])
                            if v["judge"] == ja), None)
                v_b = next((v for v in r.get("verdicts", [])
                            if v["judge"] == jb), None)
                if not v_a or not v_b:
                    continue
                if v_a["ab"] == VERDICT_ERROR or v_b["ab"] == VERDICT_ERROR:
                    continue
                total += 1
                if v_a["ab"] == v_b["ab"]:
                    agree += 1
            pct = (agree / total * 100) if total else 0.0
            out[f"{ja} || {jb}"] = round(pct, 1)
    return out


def _build_judge_pool(claude_judge_model: str) -> list[tuple[str, str]]:
    """Default 4-judge pool. Empty key entries silently skipped at runtime."""
    return [
        ("groq", "llama-3.3-70b-versatile"),
        ("anthropic", claude_judge_model),
        ("gemini", "gemini-2.5-pro"),
        ("cohere", "command-r-plus-08-2024"),
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--gpt-oss-model", default="openai/gpt-oss-120b")
    p.add_argument("--claude-model", default="claude-sonnet-4-5-20250929")
    p.add_argument("--claude-judge-model", default="claude-sonnet-4-5-20250929",
                   help="Claude model used as a *judge* (separate from the "
                        "head-to-head Claude under test).")
    args = p.parse_args()

    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]

    keys = {
        "groq": os.getenv("GROQ_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "gemini": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        "cohere": os.getenv("COHERE_API_KEY"),
    }
    if not (keys["groq"] and keys["anthropic"]):
        print("MISSING KEYS — set GROQ_API_KEY + ANTHROPIC_API_KEY", file=sys.stderr)
        return 2

    judges = _build_judge_pool(args.claude_judge_model)
    available = [j for j in judges if keys.get(j[0])]
    skipped = [j for j in judges if not keys.get(j[0])]
    judge_labels = [f"{p_}/{m}" for p_, m in available]
    if skipped:
        print(f"NOTE: skipping judges (missing keys): "
              f"{', '.join(f'{p_}/{m}' for p_, m in skipped)}", file=sys.stderr)

    print(f"=== {len(rows)} prompt × {len(available)*2} verdict "
          f"({len(available)} judge × position swap) ===")

    t0 = time.time()
    results = []
    for row in rows:
        r = run_one(row, gpt_oss_model=args.gpt_oss_model,
                    claude_model=args.claude_model,
                    judge_models=available,
                    keys=keys)
        results.append(r)
        sm = sum(1 for v in r.get("verdicts", []) if not v.get("consistent"))
        print(f"[{r['id']}] {r['consensus']} ({r['confidence']}) "
              f"swap_mismatch={sm}/{len(available)}")

    duration = time.time() - t0

    # ── aggregate ────────────────────────────────────────────────────
    summary = Counter(r["consensus"] for r in results)
    confident = [r for r in results
                 if r["confidence"] in ("confident_strong", "confident_weak")]
    confident_contested = [r for r in confident
                           if r["consensus"] in ("gpt_oss_wins", "claude_wins")]
    win_count = sum(1 for r in confident_contested
                    if r["consensus"] == "gpt_oss_wins")
    win_rate_confident = (win_count / len(confident_contested) * 100) \
        if confident_contested else 0.0
    ci_low, ci_high = _wilson_ci(win_count, len(confident_contested))

    judge_breakdown = _per_judge_breakdown(results, judge_labels)
    pair_agree = _pairwise_agreement(results, judge_labels)

    # Aggregate position bias = avg across judges
    if judge_breakdown:
        avg_pos_bias = sum(b["position_bias_pct"]
                           for b in judge_breakdown.values()) / len(judge_breakdown)
    else:
        avg_pos_bias = 0.0

    # ── write artifact ───────────────────────────────────────────────
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    md.append("# Win-rate Consensus Eval v2 (4-judge bias-controlled)\n")
    md.append(f"> Generated: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}"
              f" · duration: {duration:.1f}s · {len(rows)} rows\n")
    md.append(f"> GPT-OSS: `{args.gpt_oss_model}` · Claude (under test): `{args.claude_model}`\n")
    md.append(f"> Judges: {', '.join(judge_labels) or '(none)'}"
              f" — each with A/B position swap → {len(judge_labels)*2} verdicts/prompt\n")
    if skipped:
        md.append(f"> Judges skipped (missing keys): "
                  f"{', '.join(f'{p_}/{m}' for p_, m in skipped)}\n")
    md.append("\n## Aggregate consensus\n| Bucket | Count |\n|---|---|\n")
    for k, v in summary.items():
        md.append(f"| {k} | {v} |\n")
    md.append("\n## Confidence breakdown\n")
    conf_breakdown = Counter(r["confidence"] for r in results)
    for k, v in conf_breakdown.items():
        md.append(f"- {k}: {v}\n")
    md.append("\n## Confident win-rate (>=5/8 majority on contested rows)\n")
    md.append(f"- Confident rows: {len(confident)} / {len(results)}\n")
    md.append(f"- Confident *contested* (excl. tie): {len(confident_contested)}\n")
    md.append(f"- GPT-OSS wins: {win_count}\n")
    md.append(f"- Claude wins: {len(confident_contested) - win_count}\n")
    md.append(f"- **GPT-OSS-120B confident win-rate: "
              f"{win_rate_confident:.1f}%**\n")
    md.append(f"- 95% Wilson CI: [{ci_low*100:.1f}%, {ci_high*100:.1f}%]\n")
    md.append("\n## Per-judge breakdown (AB-pass only)\n")
    md.append("| Judge | N | A wins (GPT-OSS) | B wins (Claude) | Tie | "
              "GPT-OSS win % | Position bias % |\n"
              "|---|---|---|---|---|---|---|\n")
    for label, b in judge_breakdown.items():
        md.append(f"| {label} | {b['n']} | {b['a_wins']} | {b['b_wins']} | "
                  f"{b['ties']} | {b['gpt_oss_win_pct_ab']:.1f}% | "
                  f"{b['position_bias_pct']:.1f}% |\n")
    md.append(f"\n*Average position-swap mismatch across judges: "
              f"{avg_pos_bias:.1f}%* "
              f"(higher = more order sensitivity → judge less reliable).\n")
    md.append("\n## Pairwise inter-judge agreement (AB-pass)\n")
    if pair_agree:
        md.append("| Pair | Agreement % |\n|---|---|\n")
        for k, v in pair_agree.items():
            md.append(f"| {k} | {v:.1f}% |\n")
    else:
        md.append("_Only one judge available — no pairs to report._\n")
    md.append("\n## Per-row verdicts\n")
    md.append("| id | category | consensus | confidence | swap_mismatches |\n"
              "|---|---|---|---|---|\n")
    for r in results:
        sm = sum(1 for v in r.get("verdicts", []) if not v.get("consistent"))
        md.append(f"| {r['id']} | {r.get('category','?')} | {r['consensus']} | "
                  f"{r['confidence']} | {sm}/{len(judge_labels)} |\n")

    ARTIFACT.write_text("".join(md), encoding="utf-8")
    RESULTS_JSON.write_text(json.dumps({
        "duration_s": duration,
        "n_rows": len(rows),
        "summary": dict(summary),
        "confidence_breakdown": dict(conf_breakdown),
        "win_rate_confident_pct": round(win_rate_confident, 1),
        "wilson_ci_95": [round(ci_low * 100, 1), round(ci_high * 100, 1)],
        "judges": judge_labels,
        "judges_skipped": [f"{p_}/{m}" for p_, m in skipped],
        "per_judge": judge_breakdown,
        "pairwise_agreement": pair_agree,
        "avg_position_bias_pct": round(avg_pos_bias, 1),
        "results": results,
    }, indent=2), encoding="utf-8")

    print(f"\nartifact: {ARTIFACT}")
    print(f"json:     {RESULTS_JSON}")
    print(f"win-rate (confident contested): {win_rate_confident:.1f}% "
          f"on {len(confident_contested)}/{len(results)} rows")
    print(f"95% Wilson CI: [{ci_low*100:.1f}%, {ci_high*100:.1f}%]")
    print(f"avg position bias: {avg_pos_bias:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
