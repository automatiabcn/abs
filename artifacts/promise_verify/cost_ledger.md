# Cost ledger — Groq vs Anthropic

> Generated: 2026-05-07T11:52:04+00:00 · derived from `artifacts/promise_verify/latency_benchmark.json`
> Latency run mode: `live` · N=100 prompts

## Pricing (per million tokens)

| Provider | Model | Input $/Mtok | Output $/Mtok |
|---|---|---|---|
| groq | `openai/gpt-oss-120b` | $0.00 | $0.00 |
| anthropic | `claude-sonnet-4-5-20250929` | $3.00 | $15.00 |

## Per-prompt cost (mean across the run)

| Provider | Mean input tokens | Mean output tokens | Cost / prompt |
|---|---|---|---|
| Groq | 144.6 | 562.1 | $0.000000 |
| Anthropic | 92.1 | 475.9 | $0.007401 |

## Monthly projection (USD)

| Workload | Groq monthly | Anthropic monthly |
|---|---|---|
| 1,000 prompts/mo | $0.00 | $7.41 |
| 10,000 prompts/mo | $0.00 | $74.15 |

At 1 000 prompts / month, Anthropic spend ($7.41) stays inside the $20 Claude Plus budget — quota_monitor (95 % hard block) keeps it that way at higher workloads.

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
