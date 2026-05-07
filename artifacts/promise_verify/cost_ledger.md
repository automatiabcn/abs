# Cost ledger — Groq vs Anthropic

> Generated: 2026-05-07T10:41:34+00:00 · derived from `artifacts/promise_verify/latency_benchmark.json`
> Latency run mode: `live-no-anthropic` · N=100 prompts
> ⚠️ Anthropic side did not run live in the latency benchmark; per-prompt cost is projected from **Groq token counts** as a floor estimate. Real Sonnet 4.5 outputs are typically longer, so a live re-run will likely raise these numbers, not lower them.

## Pricing (per million tokens)

| Provider | Model | Input $/Mtok | Output $/Mtok |
|---|---|---|---|
| groq | `openai/gpt-oss-120b` | $0.00 | $0.00 |
| anthropic | `claude-sonnet-4-5-20250929` | $3.00 | $15.00 |

## Per-prompt cost (mean across the run)

| Provider | Mean input tokens | Mean output tokens | Cost / prompt |
|---|---|---|---|
| Groq | 144.6 | 564.6 | $0.000000 |
| Anthropic | 144.6 | 564.6 | $0.008892 |

## Monthly projection (USD)

| Workload | Groq monthly | Anthropic monthly |
|---|---|---|
| 1,000 prompts/mo | $0.00 | $8.90 |
| 10,000 prompts/mo | $0.00 | $89.03 |

At 1 000 prompts / month, Anthropic spend ($8.90) stays inside the $20 Claude Plus budget — quota_monitor (95 % hard block) keeps it that way at higher workloads.

## What this ledger does NOT include

- Cohere embedding/rerank free-tier (separate quota, not LLM tokens)
- Gemini 2.5 Flash / Pro multimodal free-tier (out of scope here; cascade evidence in `cascade_smoke.md`)
- Cloudflare Workers AI free allotment
- Local Ollama models (sunk cost, $0 marginal)

## Reproduce

```bash
python scripts/eval/cost_calculator.py
```

No network call. Re-runs are idempotent for a fixed `latency_benchmark.json`.
