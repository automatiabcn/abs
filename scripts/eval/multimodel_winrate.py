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
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
COHERE_BASE = "https://api.cohere.com/v2/chat"


class RateLimitError(Exception):
    """Raised when a provider returns 429 (rate limited).

    Carries `retry_after` seconds (float, may be 0 if not advertised) so
    the retry wrapper can honour Retry-After hints when the provider
    sets them.
    """

    def __init__(self, provider: str, status: int, retry_after: float = 0.0,
                 body: str = ""):
        self.provider = provider
        self.status = status
        self.retry_after = retry_after
        self.body = body[:300]
        super().__init__(f"{provider} rate limited ({status}): {self.body}")


def _http_post_json(url: str, body: dict, headers: dict,
                    timeout: float = 60.0, *, provider: str = "?") -> dict:
    """POST + JSON. Raises RateLimitError on 429, generic on others."""
    if _HAS_HTTPX:
        # httpx ships its own CA bundle (certifi) so it works on a
        # fresh macOS Python install where stdlib SSL has no trust
        # anchors yet.
        with httpx.Client(timeout=timeout) as client:  # type: ignore[possibly-unbound-variable]
            resp = client.post(url, json=body, headers=headers)
            if resp.status_code == 429:
                ra = resp.headers.get("retry-after", "0")
                try:
                    ra_f = float(ra)
                except ValueError:
                    ra_f = 0.0
                raise RateLimitError(provider, 429, ra_f, resp.text)
            resp.raise_for_status()
            return resp.json()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            ra = exc.headers.get("retry-after", "0") if exc.headers else "0"
            try:
                ra_f = float(ra)
            except ValueError:
                ra_f = 0.0
            raise RateLimitError(provider, 429, ra_f,
                                 exc.read().decode("utf-8", "replace")) from exc
        raise


def _post_with_retry(url: str, body: dict, headers: dict,
                     *, provider: str, timeout: float = 60.0,
                     max_retries: int = 5,
                     base_sleep: float = 1.0,
                     max_sleep: float = 60.0) -> dict:
    """POST with exponential backoff on RateLimitError.

    1s, 2s, 4s, 8s, 16s, capped at 60s. After max_retries the last
    RateLimitError is re-raised; callers up the stack convert it into
    an explicit verdict="error" sample (no silent TIE).
    """
    delay = base_sleep
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return _http_post_json(url, body, headers, timeout, provider=provider)
        except RateLimitError as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            sleep_for = max(exc.retry_after, delay)
            sleep_for = min(sleep_for, max_sleep)
            time.sleep(sleep_for)
            delay = min(delay * 2, max_sleep)
    if last_exc:
        raise last_exc  # pragma: no cover — unreachable but type-safe
    raise RuntimeError("retry loop exited without result")  # pragma: no cover


class AnthropicThrottle:
    """Plus-tier throttle: ≤30 calls per 15-min window.

    Anthropic Plus quota is roughly 50/5h. Capping at 30/15min keeps the
    consensus eval well below the budget while letting bursts proceed.
    Singleton-style: callers `acquire()` before each Anthropic call.
    """

    WINDOW_SEC = 15 * 60
    MAX_CALLS = 30

    def __init__(self) -> None:
        self._timestamps: list[float] = []

    def acquire(self) -> None:
        now = time.time()
        self._timestamps = [t for t in self._timestamps
                            if now - t < self.WINDOW_SEC]
        if len(self._timestamps) >= self.MAX_CALLS:
            wait = self.WINDOW_SEC - (now - self._timestamps[0]) + 1.0
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            self._timestamps = [t for t in self._timestamps
                                if now - t < self.WINDOW_SEC]
        self._timestamps.append(now)


_anthropic_throttle = AnthropicThrottle()


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
    payload = _post_with_retry(GROQ_BASE, body, headers, provider="groq")
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
    _anthropic_throttle.acquire()
    payload = _post_with_retry(ANTHROPIC_BASE, body, headers, provider="anthropic")
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def call_gemini(prompt: str, model: str, api_key: str) -> str:
    """Google Gemini generateContent REST.

    Mirror of `call_groq`/`call_claude`: returns plain text. Caller
    handles parser noise (single-letter A/B/TIE responses).
    """
    url = f"{GEMINI_BASE}/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800,
        },
    }
    headers = {"Content-Type": "application/json"}
    payload = _post_with_retry(url, body, headers, provider="gemini")
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", []) or []
    return "".join(p.get("text", "") for p in parts if "text" in p)


def call_cohere(prompt: str, model: str, api_key: str) -> str:
    """Cohere v2 chat REST.

    Sync httpx; matches the rest of this module rather than the
    backend's AsyncClientV2 SDK so the eval harness has no extra deps.
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = _post_with_retry(COHERE_BASE, body, headers, provider="cohere")
    msg = payload.get("message") or {}
    content = msg.get("content") or []
    return "".join(p.get("text", "") for p in content if p.get("type") == "text")


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


def judge(task: str, traits: list[str], a: str, b: str, api_key: str,
          judge_model: str = "llama-3.3-70b-versatile",
          judge_provider: str = "groq",
          claude_key: str | None = None) -> str:
    """Return 'A' / 'B' / 'TIE'. Defaults to TIE on parser noise.

    judge_provider: 'groq' (default, fast/free) | 'anthropic' (bias-control via Claude)
    """
    prompt = JUDGE_PROMPT.format(
        task=task,
        traits="; ".join(traits),
        a=a[:4000],
        b=b[:4000],
    )
    if judge_provider == "anthropic" and claude_key:
        raw = call_claude(prompt, model=judge_model, api_key=claude_key)
    else:
        raw = call_groq(prompt, model=judge_model, api_key=api_key)
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
    judge_provider: str = "groq",
    judge_model: str = "llama-3.3-70b-versatile",
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
            task=task,
            traits=row.get("expected_traits", row.get("traits", [])),
            a=out["gpt_oss_response"],
            b=out["claude_response"],
            api_key=groq_key,
            judge_model=judge_model,
            judge_provider=judge_provider,
            claude_key=claude_key,
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
    parser.add_argument(
        "--judge-provider", default="groq",
        choices=["groq", "anthropic"],
        help="Judge LLM provider — groq=Llama free (fast), anthropic=Claude (bias-control).",
    )
    parser.add_argument(
        "--judge-model", default="llama-3.3-70b-versatile",
        help="Judge model id (e.g. llama-3.3-70b-versatile or claude-sonnet-4-5-20250929).",
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
                judge_provider=args.judge_provider,
                judge_model=args.judge_model,
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
