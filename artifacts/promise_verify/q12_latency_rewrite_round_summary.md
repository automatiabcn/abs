# Sprint Q12 latency / cost / redundancy rewrite — round summary

> Branch: `feat/sprint-q12-deep-quality`
> Worker: ABS Worker Q8
> Completed: 2026-05-07 (UTC)

## Round map

| Round | Deliverable | Commit |
|-------|-------------|--------|
| R1 | `scripts/eval/latency_benchmark.py` + N=100 live Groq run + artifacts | `1854dea` |
| R2 | `scripts/eval/cost_calculator.py` + cost ledger artifact | `d31af5a` |
| R3 | `scripts/eval/cascade_smoke.py` + 7/7-round smoke artifact | `7a84493` |
| R4 | `docs/ABS_HYBRID_TIER_PROMISE.md` v1.2 → v1.3 (Quality bar deleted, "What we measure / What we do NOT claim" added) | `a84f08a` |
| R5 | `core/backend/tests/test_promise_v6_latency_cost_cascade.py` (7 new tests) + doc retraction phrasing fix | `8021c42` |
| R6 | image rebuild + this round summary | (this commit) |

## Mandatory verification fields

- **pytest_full_suite:** `1822 passed, 10 skipped, 3 deselected` in 184.87 s with the brief's three ignores (`test_providers.py`, `test_q03_real_saas_backends.py`, `test_update_channel.py`). Baseline before R5 was 1815 (per memory `session_resume_state_winrate_consensus_v2.md`); +7 new tests landed in `test_promise_v6_latency_cost_cascade.py` and the suite went 1815 → 1822 with **zero new failures**.
- **image_rebuilt_at:** `2026-05-07T10:50Z` host wall-clock — `docker compose build backend` from `infra/docker-compose.yml`. Result tag `docker.io/library/infra-backend:latest`, manifest list digest `sha256:2978ca27c19d6d5e41c24a8bbd6fd24d47d4530399681444a0331073f8cbc188`. Most layers were CACHED because the only Python sources that changed were under `scripts/eval/` (not in the image) and `core/backend/tests/` (test stage); confirmed by `docker image inspect`.
- **live_path_verified:**
  - R1 — live N=100 Groq run, `mode: live-no-anthropic` (no `ANTHROPIC_API_KEY` in this env, so the artifact records `anthropic_unavailable` honestly): P50=5829.2 ms, P95=7312.3 ms, mean=5076.1 ms, 0 errors, 14 462 input + 56 458 output tokens, duration 507.7 s.
  - R3 — `cascade_smoke.py` 7/7 rounds exercise the production `app.cascade.orchestrator.call_with_cascade` code path with stub providers (no HTTP).
  - R5 — pytest re-ran cascade smoke as a subprocess and asserted 7/7 + 6-provider chain.

## Forbidden-call audit

The brief's hard prohibitions were honoured:

- **Cohere API call count: 0** in this round series. The Cohere SDK was not imported by any of the new scripts; the only code path that *can* call Cohere (`scripts/eval/winrate_consensus.py`) was not invoked.
- **Gemini API call count: 0**. Same logic — `call_gemini` lives in `multimodel_winrate.py` but was not entered.
- **No multi-judge consensus eval was resurrected.** The R4 PROMISE.md edit explicitly retracts the methodology and adds a structural test (#6 in the new file) that fails if the "Quality bar" header or the literal `≥50 % win-rate` string ever come back.
- **No selective subset.** Full-suite pytest with the documented three ignores only.

## Customer-facing artifacts produced

- `artifacts/promise_verify/latency_benchmark.{md,json}` — N=100 wall-clock run, Groq side live, Anthropic gated.
- `artifacts/promise_verify/cost_ledger.{md,json}` — pure-arithmetic cost projection, $0/prompt Groq, $0.0089/prompt Anthropic floor estimate, $8.90 / month at 1 000 prompts (under $20 Plus budget).
- `artifacts/promise_verify/cascade_smoke.{md,json}` — 7/7 kill-each rounds against the production cascade orchestrator.
- `docs/ABS_HYBRID_TIER_PROMISE.md` v1.3 — three judge-free promises, one explicit retraction.

## Open follow-ups (not in scope for this round)

1. Founder live re-run with `ANTHROPIC_API_KEY` set so the speedup column in `latency_benchmark.md` flips from `unmeasured` to a concrete N×.
2. Observability dashboard panel that scrapes `latency_benchmark.json` weekly and tracks Groq P50/P95 drift over time.
3. The `core/backend/core/`, `data/`, and `logs/` directories that appeared as untracked in the repo are pre-existing artefacts of the running dev compose stack and were intentionally left untouched.
