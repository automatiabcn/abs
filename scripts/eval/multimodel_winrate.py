"""BUG-V4 — Sprint 13 multi-model win-rate harness.

The PROMISE.md vow:
  "Sprint 13 multi-model ensemble (T-049..T-056) verified that
   GPT-OSS-120B baseline answers reach >=50 % win-rate against
   Claude Opus on the golden eval set."

This script makes that vow falsifiable. It walks
`core/backend/tests/fixtures/golden_eval_multimodel.json`, calls the
configured GPT-OSS-120B and Claude Opus providers in parallel, then
scores each pair with a free-tier judge model. The judge writes a
verdict per row (gpt_oss_wins | claude_wins | tie) and the script
aggregates the totals into a markdown artifact under
`artifacts/promise_verify/sprint_13_winrate.md`.

Honest gating:
  - If `ANTHROPIC_API_KEY` is unset the Claude side is skipped and the
    artifact records `claude_unavailable` rather than fabricating a
    score. Win-rate is reported as `unmeasured` in that case.
  - Same for `GROQ_API_KEY` (judge + GPT-OSS path both rely on it).

Usage:
  python scripts/eval/multimodel_winrate.py            # full live run
  python scripts/eval/multimodel_winrate.py --limit 5  # quick smoke
  python scripts/eval/multimodel_winrate.py --offline  # contract-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any

try:
    import httpx  # backend venv has it; falls back to urllib otherwise.

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    _HAS_HTTPX = False

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "core/backend/tests/fixtures/golden_eval_multimodel.json"
ARTIFACT = ROOT / "artifacts/promise_verify/sprint_13_winrate.md"
RESULTS_JSON = ROOT / "artifacts/promise_verify/sprint_13_winrate.json"

GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"
ANTHROPIC_BASE = "https://api.anthropic.com/v1/messages"


def _http_post_json(url: str, body: dict, headers: dict, timeout: float = 60.0) -> dict:
    if _HAS_HTTPX:
        # httpx ships its own CA bundle (certifi) so it works on a
        # fresh macOS Python install where stdlib SSL has no trust
        # anchors yet.
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_groq(prompt: str, model: str, api_key: str) -> str:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = _http_post_json(GROQ_BASE, body, headers)
    return payload["choices"][0]["message"]["content"]


def call_claude(prompt: str, model: str, api_key: str) -> str:
    body = {
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = _http_post_json(ANTHROPIC_BASE, body, headers)
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


JUDGE_PROMPT = """You are an impartial evaluator. Two assistants
answered the same task. Score which answer better satisfies the
expected_traits and the task instructions. Reply with EXACTLY one
word: A, B, or TIE.

TASK:
{task}

EXPECTED TRAITS:
{traits}

ANSWER A:
{a}

ANSWER B:
{b}

Reply with A, B, or TIE only.
"""


def judge(task: str, traits: list[str], a: str, b: str, api_key: str) -> str:
    """Return 'A' / 'B' / 'TIE'. Defaults to TIE on parser noise."""
    prompt = JUDGE_PROMPT.format(
        task=task,
        traits="; ".join(traits),
        a=a[:4000],
        b=b[:4000],
    )
    raw = call_groq(prompt, model="llama-3.3-70b-versatile", api_key=api_key)
    upper = raw.strip().upper()
    if upper.startswith("A"):
        return "A"
    if upper.startswith("B"):
        return "B"
    return "TIE"


def run_one(
    row: dict[str, Any],
    *,
    groq_key: str | None,
    claude_key: str | None,
    gpt_oss_model: str,
    claude_model: str,
) -> dict[str, Any]:
    task = row["task"]
    out: dict[str, Any] = {
        "id": row["id"],
        "category": row["category"],
        "verdict": "skipped",
    }
    if not groq_key:
        out["error"] = "groq_unavailable"
        return out
    try:
        out["gpt_oss_response"] = call_groq(task, gpt_oss_model, groq_key)
    except Exception as exc:  # noqa: BLE001 — log every transport failure
        out["error"] = f"gpt_oss_call_failed: {exc}"
        return out
    if not claude_key:
        out["verdict"] = "claude_unavailable"
        return out
    try:
        out["claude_response"] = call_claude(task, claude_model, claude_key)
    except Exception as exc:  # noqa: BLE001 — log every transport failure
        out["error"] = f"claude_call_failed: {exc}"
        return out
    # GPT-OSS answer = A, Claude answer = B for the judge.
    try:
        verdict_letter = judge(
            task,
            row.get("expected_traits", []),
            out["gpt_oss_response"],
            out["claude_response"],
            groq_key,
        )
    except Exception as exc:  # noqa: BLE001 — log judge transport failures
        out["error"] = f"judge_failed: {exc}"
        return out
    out["verdict"] = {
        "A": "gpt_oss_wins",
        "B": "claude_wins",
        "TIE": "tie",
    }[verdict_letter]
    return out


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"gpt_oss_wins": 0, "claude_wins": 0, "tie": 0,
              "claude_unavailable": 0, "skipped": 0, "error": 0}
    for r in results:
        if "error" in r:
            counts["error"] += 1
            continue
        verdict = r.get("verdict", "skipped")
        counts[verdict] = counts.get(verdict, 0) + 1
    contested = counts["gpt_oss_wins"] + counts["claude_wins"] + counts["tie"]
    if contested == 0:
        win_rate: float | None = None
    else:
        # win-rate convention from brief: GPT-OSS win = 1.0, tie = 0.5
        win_rate = (counts["gpt_oss_wins"] + 0.5 * counts["tie"]) / contested
    return {"counts": counts, "contested": contested, "win_rate": win_rate}


def render_markdown(
    *,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    gpt_oss_model: str,
    claude_model: str,
    started_at: str,
    finished_at: str,
    duration_s: float,
    mode: str,
) -> str:
    lines: list[str] = []
    lines.append("# Sprint 13 multi-model win-rate evidence\n")
    lines.append(f"> Generated: {finished_at} · mode: `{mode}` · duration: {duration_s:.1f}s\n")
    lines.append(f"> Dataset: `core/backend/tests/fixtures/golden_eval_multimodel.json` ({len(results)} rows)\n")
    lines.append(f"> GPT-OSS model: `{gpt_oss_model}`\n")
    lines.append(f"> Claude model: `{claude_model}`\n\n")
    lines.append("## Aggregate\n")
    counts = summary["counts"]
    lines.append("| Bucket | Count |\n|---|---|\n")
    for key, val in counts.items():
        lines.append(f"| {key} | {val} |\n")
    contested = summary["contested"]
    if summary["win_rate"] is None:
        lines.append("\n**Win-rate: unmeasured** — no head-to-head pairs were judged.\n")
    else:
        lines.append(
            f"\n**GPT-OSS-120B win-rate (vs Claude {claude_model}, "
            f"contested {contested}/{len(results)}): "
            f"{summary['win_rate'] * 100:.1f} %**\n"
        )
    lines.append("\n## First five non-trivial rows\n")
    sample = [r for r in results if r.get("verdict") not in {"skipped"}][:5]
    if not sample:
        lines.append("_No rows judged — see `claude_unavailable` count above._\n")
    else:
        lines.append("| id | category | verdict | error |\n|---|---|---|---|\n")
        for r in sample:
            lines.append(
                f"| {r['id']} | {r['category']} | {r.get('verdict','-')} | "
                f"{r.get('error','-')} |\n"
            )
    lines.append("\n## How to reproduce\n\n")
    lines.append("```bash\n")
    lines.append("# Requires GROQ_API_KEY (free) + ANTHROPIC_API_KEY (paid opt-in).\n")
    lines.append("python scripts/eval/multimodel_winrate.py\n")
    lines.append("```\n")
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Run only the first N rows (smoke).")
    parser.add_argument("--offline", action="store_true",
                        help="Contract-only run; skip live calls.")
    parser.add_argument(
        "--gpt-oss-model", default="openai/gpt-oss-120b",
        help="Groq model id for the GPT-OSS-120B path.",
    )
    parser.add_argument(
        "--claude-model", default="claude-opus-4-1-20250805",
        help="Anthropic model id for the Claude Opus path.",
    )
    args = parser.parse_args()

    if not DATASET.exists():
        print(f"dataset missing: {DATASET}", file=sys.stderr)
        return 2
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    started_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    if args.offline:
        results = [
            {"id": r["id"], "category": r["category"], "verdict": "skipped",
             "error": "offline_mode"} for r in rows
        ]
        mode = "offline"
    else:
        groq_key = os.getenv("GROQ_API_KEY") or None
        claude_key = os.getenv("ANTHROPIC_API_KEY") or None
        results = []
        for row in rows:
            r = run_one(
                row,
                groq_key=groq_key,
                claude_key=claude_key,
                gpt_oss_model=args.gpt_oss_model,
                claude_model=args.claude_model,
            )
            results.append(r)
            verdict = r.get("verdict", "?")
            err = r.get("error", "")
            print(f"[{r['id']}] {verdict} {err}".strip())
        mode = "live" if claude_key else "live-no-claude"
    duration_s = time.time() - t0
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary = aggregate(results)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        render_markdown(
            summary=summary,
            results=results,
            gpt_oss_model=args.gpt_oss_model,
            claude_model=args.claude_model,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=duration_s,
            mode=mode,
        ),
        encoding="utf-8",
    )
    RESULTS_JSON.write_text(
        json.dumps(
            {"mode": mode, "started_at": started_at, "finished_at": finished_at,
             "summary": summary, "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nartifact: {ARTIFACT}")
    print(f"json:     {RESULTS_JSON}")
    if summary["win_rate"] is not None:
        print(f"win-rate: {summary['win_rate'] * 100:.1f}%")
    else:
        print("win-rate: unmeasured (claude_unavailable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
