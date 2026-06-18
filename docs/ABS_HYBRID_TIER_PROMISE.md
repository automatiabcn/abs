# ABS Hybrid Tier Promise

> v1.3.1 · 2026-05-07 · Anthropic re-run filled live latency + cost numbers (5.26× P50, $7.41/mo @ 1k prompts)

## What ABS guarantees

If a customer pays **$20 / month for a Claude Plus subscription** and runs ABS on their own server, ABS keeps total monthly spend at the floor of:

- **Subscription:** $20 (Claude Plus)
- **Compute:** their own hardware (sunk cost)
- **Everything else ABS does:** $0

## Why this works

| Layer | Free provider | Paid alternative |
|-------|---------------|------------------|
| LLM heavy reasoning | Groq GPT-OSS-120B | Claude Opus / Sonnet (opt-in) |
| LLM general | Groq Llama 3.3 70B, Llama 4 Scout, Kimi K2, Qwen3-32B | Claude Haiku |
| Cloud LLM fallback | Cloudflare Workers AI (Kimi K2.5 256K, Llama 4 Scout, GPT-OSS) | OpenAI / Anthropic |
| Multimodal | Gemini 2.5 Flash/Pro | OpenAI Vision |
| Local LLM | Ollama (Phi-4, Gemma-2, Qwen 2.5 Coder, CodeLlama, Llava) | – |
| Embedding | Cohere `embed-english-v3.0` (free tier) + Ollama BGE | OpenAI text-embedding-3 |
| Reranker | Cohere `rerank-multilingual-v3.0` (free tier) + Qwen3 ONNX local | – |
| Meeting bot | meetily / jitsi self-host + WhisperX local | Recall.ai (~$0.50/hr) |
| TTS | Coqui XTTS-v2 + Piper | ElevenLabs (~$0.0006/char) |
| Vector DB | Qdrant self-host | Pinecone |
| Observability | LangFuse self-host | LangSmith |
| Workflow engine | Inngest dev mode + n8n self-host | Inngest cloud |

## How ABS spends Claude responsibly

When the customer opts into Claude (`ABS_ANTHROPIC_ENABLED=true` + their own `ABS_ANTHROPIC_API_KEY`):

1. **Free path first.** ABS quality pipelines (`qual_code`, `qual_analysis`, `race_code`, `cascade`) all default to Groq + Cloudflare + Gemini + Cohere + Ollama. None of those paths touch Anthropic.
2. **Quota tracker.** `app/observability/quota_monitor.py` records every Claude token to a monthly ledger. Two thresholds:
   - **80 %** → warning banner on `/admin/usage`, LangFuse trace tagged `claude_budget_warn`.
   - **95 %** → hard block (`QuotaExceeded`), automatic fallback to Groq.
3. **Pre-flight gate.** Before each Claude call, the adapter projects `used + max_tokens` and refuses up-front if that breaches 95 %.
4. **No silent overruns.** If the user's monthly token budget would be exceeded mid-run, the call returns a `ProviderError` and the cascade picks the next provider; the customer never sees a Claude bill they did not budget for.

## What we measure (and what we don't)

ABS makes three falsifiable empirical promises. Each one is judge-free, deterministic, and reproducible from a single command on the operator's own keys.

### 1. Latency — Groq is 5× faster than Anthropic at P50, 9× faster at P95

- **Result (live N=100, 2026-05-07):** Groq GPT-OSS-120B P50 = 1 789 ms, Anthropic Sonnet 4.5 P50 = 9 410 ms ⇒ **5.26× speedup at P50**, **9.43× at P95**, 7.22× at the mean. Both providers ran 100/100 successful, 0 errors. Throttle-bound wall-clock for the run was 47 minutes (Anthropic Plus 30/15-min cap).
- **Evidence:** [`artifacts/promise_verify/latency_benchmark.md`](../artifacts/promise_verify/latency_benchmark.md) (+ JSON sidecar with per-prompt timings).
- **Method:** N=100 prompts from [`core/backend/tests/fixtures/golden_eval_multimodel.json`](../core/backend/tests/fixtures/golden_eval_multimodel.json) (25 code / 25 analysis / 25 translation / 25 writing). `time.perf_counter()` is wrapped around each HTTP POST so the recorded number is wall-clock customer-felt latency, not just server-side compute.
- **Reproduce:** `python scripts/eval/latency_benchmark.py` (requires `GROQ_API_KEY`; `ANTHROPIC_API_KEY` is opt-in — when absent the artifact records `anthropic_unavailable` and leaves speedup as `unmeasured` rather than fabricating a number).

### 2. Cost — Free path is $0 / prompt; Anthropic Plus stays inside the $20 budget

- **Result (live N=100, 2026-05-07):** Groq cost / prompt = **$0.000000** (free tier). Anthropic Sonnet 4.5 cost / prompt = **$0.007401** at the measured 92 input + 476 output token mean. Monthly projection at 1 000 prompts = **$7.41** Anthropic spend (well inside the $20 Claude Plus budget); 10 000 prompts = $74.15, where the `quota_monitor` 95 %-cap fires before that lands as a real bill.
- **Evidence:** [`artifacts/promise_verify/cost_ledger.md`](../artifacts/promise_verify/cost_ledger.md) (+ JSON sidecar)
- **Method:** pure arithmetic — token counts from the latency JSON × published pricing ($3 / $15 per Mtok input/output for Sonnet 4.5; $0 for Groq GPT-OSS-120B). No LLM call, no network.
- **Customer guard:** `app/observability/quota_monitor.py` records every Claude token, warns at 80 %, hard-blocks at 95 % (`QuotaExceeded` ⇒ cascade falls back to Groq). Pre-flight gate refuses calls projected to breach 95 %.
- **Reproduce:** `python scripts/eval/cost_calculator.py`

### 3. Redundancy — The cascade survives any single-provider outage

- **Evidence:** [`artifacts/promise_verify/cascade_smoke.md`](../artifacts/promise_verify/cascade_smoke.md) (+ JSON sidecar)
- **Method:** 6 stub providers wired into production [`app/cascade/orchestrator.py`](../core/backend/app/cascade/orchestrator.py) `call_with_cascade`. 7 rounds total — 1 baseline + 6 kill-each — every round verifies the cascade falls through to the next configured provider. Stubs only; zero real API traffic so this round is rate-limit-safe.
- **Reproduce:** `python scripts/eval/cascade_smoke.py`

## What we do NOT claim

ABS does **not** claim that GPT-OSS-120B is "categorically better" than Claude Sonnet 4.5 / Opus 4.1 on output quality. We attempted a multi-judge LLM-as-judge consensus eval (4 judges × A/B position swap = 8 verdicts per prompt) and **abandoned it** on 2026-05-07 after these findings:

- **Cross-judge variance = 58 percentage points** on 30 prompts (Llama 3.3 70b judge → 80 % GPT-OSS win-rate; Sonnet 4.5 judge → 22 % — the judge favoured itself). LLM-as-judge is a noisy oracle, not a signal.
- **Position-swap mismatch = 3/3** on the very first contested prompt of the v2 4-judge run. When swapping `A` and `B` flips the verdict 100 % of the time on the first probe, the methodology is not stable enough to back any product claim.
- **Cohere/Gemini rate-limit storm** during the consensus run (24h cooldown email) — relying on four third-party APIs in the critical evaluation path adds an outage surface ABS itself doesn't have.

The legacy single-judge artifacts in [`artifacts/promise_verify/`](../artifacts/promise_verify/) (`opus_v_gptoss_*`, `sonnet_v_gptoss_*`, `winrate_consensus*`) are retained as an **audit trail of why we abandoned LLM-as-judge** for product claims. Do not cite their win-rate numbers; cite the methodology critique instead. The earlier majority-win-rate phrasing from v1.0 is **fully retracted** and will not be re-introduced.

What we observe by direct usage: GPT-OSS-120B output quality is at competitive parity with Sonnet 4.5 on this dataset. We have **not** statistically proven that and we no longer plan to — the customer's real win is the trio above (cost, latency, redundancy), all of which we can measure deterministically. Founders are encouraged to run their own eyeball N=10 on real tasks before opting in to Anthropic billing.

## What the customer sees

- **`/admin/usage` widget** — real-time `Free path: X %` + `Claude budget: Y %` tiles plus a 7-day Claude-token trend chart. Endpoint: `GET /v1/admin/usage`. Frontend: [`core/landing/app/admin/usage/page.tsx`](../core/landing/app/admin/usage/page.tsx).
- **LangFuse dashboard** — `claude_tokens_used_pct_month` time-series. Wired in [`core/backend/app/observability/quota_monitor.py`](../core/backend/app/observability/quota_monitor.py) `record()` → `langfuse.score(name=…)`. Active when `ABS_LANGFUSE_ENABLED=true` and the public/secret keys are set.
- **Audit chain** — every opt-in flip and quota-block event lands on the T-016 SOC2 audit log. Sources: [`app/observability/optin_state.py`](../core/backend/app/observability/optin_state.py) (boot-time flip detection) and [`app/observability/quota_monitor.py`](../core/backend/app/observability/quota_monitor.py) `gate()` (quota.block emit).
- **Workflow canvas** — `POST /v1/workflows/execute` returns `estimated_cost_usd`; free-tier-only plans return `0.0`, anthropic / openai nodes surface non-zero. Source: [`app/workflow_v10/runner.py`](../core/backend/app/workflow_v10/runner.py) `estimate_cost()`.

## Promise summary (one paragraph)

ABS lets the customer keep their Claude Plus subscription as a fixed-cost premium lane while doing 95 %+ of the work on free providers. The quota monitor enforces the monthly budget so a runaway workflow can never burn through the customer's Claude allowance. ABS-specific quality features (qual_code, race_code, cascade, RAG, judge) all run on free providers by default. Total cost: $20 + sunk-cost compute. No surprises.

## Sign-off

> Author: Automatia BCN engineering · 2026-04-29.
> v1.3 amendment: Sprint Q12 latency/cost/redundancy rewrite · 2026-05-07.
