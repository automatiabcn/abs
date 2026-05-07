"""Sprint Q12 — Cascade redundancy smoke (no live API calls).

Proves the customer-facing redundancy promise by exercising
`app.cascade.orchestrator.call_with_cascade` against the full
6-provider cascade chain with synthetic providers. Each round kills
one provider (forces it to raise a transient `ProviderError`) and
asserts the cascade falls through to the next.

Why this is rate-limit-safe:
  * No HTTP calls. Every provider is a stub that either returns a
    canned response or raises `ProviderError(transient=True)`.
  * Cohere + Gemini are part of the chain but are STUBS — they
    receive zero real-API traffic during this run. The 24h cooldown
    after the 2026-05-06 storm is honoured.

Output: `artifacts/promise_verify/cascade_smoke.{md,json}`.

Customer interpretation: "If any single provider goes down, ABS
keeps answering." Six rounds — five 'kill provider X' + one
'baseline, no kills' — give a 6×6 truth table the founder can show.

Usage:
  python scripts/eval/cascade_smoke.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import Any

# This script lives in scripts/eval; we need core/backend on sys.path
# so `app.providers.*` imports resolve.
ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "core/backend"
sys.path.insert(0, str(BACKEND))

# Quiet "/app/data/breaker_state.json.tmp" persist warnings on host
# runs — the breaker is happy to persist, it just needs a writable
# data dir. Ephemeral tmp is fine for a smoke.
os.environ.setdefault("ABS_DATA_DIR", tempfile.mkdtemp(prefix="cascade_smoke_"))

ARTIFACT_MD = ROOT / "artifacts/promise_verify/cascade_smoke.md"
ARTIFACT_JSON = ROOT / "artifacts/promise_verify/cascade_smoke.json"


def _import_app():
    """Defer app.* imports until path mutation above lands."""
    from app.cascade import orchestrator as orch_mod
    from app.providers.base import BaseProvider
    from app.providers.schemas import ProviderError, ProviderResponse
    from app.providers.cascade import PROVIDER_ORDER_PAID_FIRST
    return orch_mod, BaseProvider, ProviderError, ProviderResponse, PROVIDER_ORDER_PAID_FIRST


CASCADE_PROMPT = "Cascade redundancy smoke prompt — single deterministic input."


async def run_one_kill(*, provider_to_kill: str | None,
                       chain: tuple[str, ...]) -> dict[str, Any]:
    """One smoke round.

    `provider_to_kill=None` → baseline; primary should answer first.
    Otherwise that provider raises transient ProviderError so the
    cascade falls through to the next configured one.
    """
    orch_mod, BaseProvider, ProviderError, ProviderResponse, _ = _import_app()

    class _StubOk(BaseProvider):
        def __init__(self, label: str):
            self._label = label

        @property
        def name(self) -> str:  # type: ignore[override]
            return self._label

        async def call(self, prompt, model=None, **kw):
            return ProviderResponse(
                text=f"ok:{self._label}", model=model or "smoke",
                provider=self._label, elapsed_ms=1,
            )

    class _StubFail(BaseProvider):
        def __init__(self, label: str):
            self._label = label

        @property
        def name(self) -> str:  # type: ignore[override]
            return self._label

        async def call(self, prompt, model=None, **kw):
            raise ProviderError(
                f"{self._label} simulated outage",
                provider=self._label, transient=True,
            )

    registry: dict[str, Any] = {}
    for prov in chain:
        if prov == provider_to_kill:
            registry[prov] = _StubFail(prov)
        else:
            registry[prov] = _StubOk(prov)

    # Each round starts with a fresh cache + circuit-breaker state so
    # one round's kill doesn't carry into the next (the breaker would
    # otherwise stay open for 60s after a fail).
    await orch_mod.default_cache.clear()
    orch_mod.default_breaker._states.clear()  # type: ignore[attr-defined]

    # Patch the provider lookup. We can't use monkeypatch (no pytest
    # fixture); plain attribute swap with restoration in finally.
    original = orch_mod.get_provider
    orch_mod.get_provider = lambda n: registry[n]
    t0 = time.perf_counter()
    error: str | None = None
    answered_by: str | None = None
    try:
        resp = await orch_mod.call_with_cascade(
            CASCADE_PROMPT,
            primary=chain[0],
            fallbacks=chain[1:],
            model="smoke",
            use_cache=False,
        )
        answered_by = resp.provider
    except ProviderError as exc:
        error = f"cascade exhausted: {exc}"
    finally:
        orch_mod.get_provider = original

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    expected_answerer = chain[0] if provider_to_kill is None else (
        next((p for p in chain if p != provider_to_kill), None)
    )
    pass_ = (error is None) and (answered_by == expected_answerer)

    return {
        "killed": provider_to_kill,
        "chain": list(chain),
        "expected_answerer": expected_answerer,
        "actual_answerer": answered_by,
        "pass": pass_,
        "error": error,
        "elapsed_ms": round(elapsed_ms, 2),
    }


async def run_smoke() -> dict[str, Any]:
    """Run baseline + one round per provider in the paid-first chain."""
    _, _, _, _, chain = _import_app()
    rounds: list[dict[str, Any]] = []

    rounds.append(await run_one_kill(provider_to_kill=None, chain=chain))
    for prov in chain:
        rounds.append(await run_one_kill(provider_to_kill=prov, chain=chain))

    passed = sum(1 for r in rounds if r["pass"])
    return {
        "chain": list(chain),
        "rounds": rounds,
        "passed": passed,
        "total": len(rounds),
    }


def render_markdown(report: dict[str, Any], *, finished_at: str,
                    duration_s: float) -> str:
    lines: list[str] = []
    lines.append("# Cascade redundancy smoke\n\n")
    lines.append(
        f"> Generated: {finished_at} · duration: {duration_s:.2f}s · "
        f"`{report['passed']}/{report['total']}` rounds green\n\n"
    )
    lines.append(
        "Each round monkey-patches the provider registry: every provider "
        "in the chain is a stub that either returns `ok:<provider>` or "
        "raises a transient `ProviderError`. **No real API calls** — "
        "this is a contract smoke for the cascade orchestrator's "
        "fallthrough logic, executed against the production "
        "`app.cascade.orchestrator.call_with_cascade` code path.\n\n"
    )
    lines.append(
        f"Chain under test (paid-first): "
        f"`{' → '.join(report['chain'])}`.\n\n"
    )
    lines.append("## Rounds\n\n")
    lines.append(
        "| Killed | Chain | Expected answerer | Actual answerer | "
        "Elapsed (ms) | Pass |\n"
    )
    lines.append("|---|---|---|---|---|---|\n")
    for r in report["rounds"]:
        killed = r["killed"] or "—"
        chain = " → ".join(r["chain"])
        lines.append(
            f"| `{killed}` | {chain} | `{r['expected_answerer']}` | "
            f"`{r['actual_answerer'] or '—'}` | {r['elapsed_ms']} | "
            f"{'✅' if r['pass'] else '❌'} |\n"
        )
    lines.append("\n## Customer interpretation\n\n")
    lines.append(
        "If any one of the six providers becomes unavailable, the "
        "cascade falls through to the next configured provider on the "
        "same request. The customer never observes a hard 5xx unless "
        "**every** provider in the chain is simultaneously down — a "
        "scenario this smoke covers indirectly: zero remaining "
        "providers ⇒ `ProviderError` re-raised on the boundary, where "
        "the gateway returns 503 with the `configure-key` CTA.\n"
    )
    lines.append("\n## What this smoke does NOT prove\n\n")
    lines.append(
        "- It does not measure real provider latency under failure "
        "(see `latency_benchmark.md` for the live Groq/Anthropic "
        "numbers).\n"
    )
    lines.append(
        "- It does not exercise rate-limit recovery (`429 + "
        "Retry-After`), circuit-breaker windows, or partial outages "
        "where one provider returns 5xx intermittently — those have "
        "dedicated tests in `test_cascade*.py`.\n"
    )
    lines.append(
        "- It uses stub providers; quality of the answer is out of "
        "scope. PROMISE.md \"What we do NOT claim\" governs that.\n"
    )
    lines.append("\n## Reproduce\n\n```bash\npython scripts/eval/cascade_smoke.py\n```\n")
    return "".join(lines)


def main() -> int:
    started_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    report = asyncio.run(run_smoke())
    duration_s = time.time() - t0
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    ARTIFACT_MD.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_MD.write_text(
        render_markdown(report, finished_at=finished_at, duration_s=duration_s),
        encoding="utf-8",
    )
    ARTIFACT_JSON.write_text(
        json.dumps(
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_s": round(duration_s, 3),
                "report": report,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"artifact: {ARTIFACT_MD}")
    print(f"json:     {ARTIFACT_JSON}")
    print(f"result:   {report['passed']}/{report['total']} rounds passed")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
