# Founder Tester Session — Fix Round 3 close-out

> Trigger: founder Playwright quality v2 (2026-05-05) — 8 cascade tasks issued
> with `skip_paid_providers:true` all routed to Anthropic (provider mix
> `{"anthropic": 8}`, ~1500 paid tokens, cost savings = 0).
>
> Branch: `feat/sprint-q12-deep-quality`
> Date: 2026-05-05

---

## Bugs closed

### BUG-7 HIGH — `skip_paid_providers` flag honor

**Root cause:** `app/providers/cascade.get_active_providers` had no `skip_paid`
parameter; `app/api/cascade.run` never forwarded the body flag; Pydantic
schema (`CascadeRequest`) didn't expose the flag at all.

**Fix:**
- `app/providers/cascade.py` — `get_active_providers(prefer, skip_paid=False)`
  filters `PAID_PROVIDERS = {"anthropic"}` and swaps base order to
  `PROVIDER_ORDER_FREE_FIRST` when `skip_paid=True`.
- `app/api/cascade.py` — `CascadeRequest.skip_paid_providers: bool = False`
  added; route forwards it to `get_active_providers`; new 503 message
  `no_free_providers_configured` when chain empties under `skip_paid=True`.

### BUG-8 MED — Provider chain order constants

**Fix:** Two tuples shipped:
- `PROVIDER_ORDER_PAID_FIRST = (anthropic, groq, cerebras, gemini, cloudflare, cohere)` — default; quality first.
- `PROVIDER_ORDER_FREE_FIRST = (groq, cerebras, gemini, cohere, cloudflare)` — `groq` leads (Llama 3.3 70B + GPT-OSS 120B best free quality, lowest p95).
- Back-compat alias `PROVIDER_ORDER = PROVIDER_ORDER_PAID_FIRST` so existing imports keep working.

---

## Verification

### pytest_full_suite

```
1781 passed / 10 skipped / 3 deselected / 0 fail / 0 error
runtime: 181.72s
ignored (per discipline rule):
  - tests/test_providers.py
  - tests/test_q03_real_saas_backends.py
  - tests/test_update_channel.py
```

Full subset rule honoured (S5+S10+S11+S12 dersi). No selective subset
"clean" claims.

Backend baseline before this round: 1775 passed.
Net delta: +6 (3 unit-level ordering + 3 route-level skip_paid HTTP).

### image_rebuilt_at

`infra-backend:latest` rebuilt 2026-05-05 21:38:11 +0200 CEST,
`docker compose up -d backend` recreated container `infra-backend-1`.

### live_path_verified: true

Live curl evidence (production-like docker stack, real provider keys
in `infra/.env`, anthropic_mock OFF):

**A) skip_paid=true → groq (was anthropic):**
```
provider=groq tokens=72 elapsed=680ms model=llama-3.1-8b-instant
```

**B) skip_paid=false → anthropic primary (regression guard):**
```
provider=anthropic tokens=45 elapsed=891ms model=claude-haiku-4-5-20251001
```

**C) skip_paid=true + only anthropic key (unit test only — would require
wiping live env):** unit `test_cascade_skip_paid_no_free_providers_returns_503`
asserts 503 + body contains `no_free_providers_configured`.

### provider_routed (8-prompt founder regression)

```
prompt              provider     tokens   elapsed
simple_tr           groq         62       233ms
simple_en           groq         62       198ms
analysis            groq         61       296ms
code                groq         61       209ms
reasoning           groq         62       224ms
translation         groq         61       186ms
long_context        groq         62       179ms
classification      groq         61       209ms
```

Pre-fix mix: `{"anthropic": 8}` — Round 3 mix: `{"groq": 8}`. Cost savings
on free path = 100% per request (zero anthropic spend).

---

## Files touched

```
core/backend/app/providers/cascade.py    +25 / -8     # PAID_PROVIDERS + 2 chains + skip_paid
core/backend/app/api/cascade.py          +12 / -2     # CascadeRequest field + 503 branches
core/backend/tests/test_q12_skip_paid_honor.py  NEW   # 6 tests (3 unit + 3 route)
artifacts/founder_test_fix_3/round_3.md  NEW   # this report
```

---

## Round commits

```
b02aa5d fix(founder-test/round-2): cascade live wiring + workflow LLM + RAG cookie + 2 infra config — pytest 1755→1775
38e0b1b docs(agent-tasks): Round 2 + Q12 session briefs + Sprint 21 perf + founder test artifacts
<R3>    fix(founder-test/round-3): skip_paid_providers honor + free-first chain — pytest 1775→1781
```

---

## Founder Playwright re-run readiness

Expected next session evidence:
- 8 cascade tasks × `skip_paid_providers:true` → 0 anthropic, free-only mix.
- With orchestrator-level fail-over still active, real-world traffic may
  shuffle across `groq/cerebras/gemini/cohere/cloudflare` if `groq` rate-limits;
  current /tmp/founder_quality_v2 evidence showed `groq` happy-path 8/8.
- Default flow (no `skip_paid_providers` flag) keeps anthropic primary.
