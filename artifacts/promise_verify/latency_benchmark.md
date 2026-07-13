# Latency benchmark — Groq vs Anthropic

> Generated: 2026-05-07T11:51:33+00:00 · mode: `live` · duration: 2818.9s
> Dataset: `core/backend/tests/fixtures/golden_eval_multimodel.json` (100 prompts)
> Groq model: `openai/gpt-oss-120b`
> Anthropic model: `claude-sonnet-4-5-20250929`

## Wall-clock latency

| Provider | n_ok | errors | P50 (ms) | P95 (ms) | mean (ms) | stdev (ms) |
|---|---|---|---|---|---|---|
| Groq GPT-OSS-120B | 100 | 0 | 1788.9 | 2066.7 | 1418.5 | 639.4 |
| Anthropic Sonnet 4.5 | 100 | 0 | 9410.0 | 19492.1 | 10239.3 | 5638.8 |

## Speedup (Anthropic / Groq)

| Metric | Multiplier |
|---|---|
| P50 | 5.26× |
| P95 | 9.43× |
| mean | 7.22× |

## Token usage (sum across all prompts)

| Provider | Input tokens | Output tokens |
|---|---|---|
| Groq | 14462 | 56212 |
| Anthropic | 9214 | 47588 |

## Notes

- Wall-clock timing uses `time.perf_counter()` around each HTTP POST, including TLS handshake — that is the customer-felt latency.
- `AnthropicThrottle` (≤30 calls / 15-min) is honoured to keep the Plus tier within budget during the run.
- No LLM-as-judge is invoked; this script makes no claim about output quality. See `cost_ledger.md` and `cascade_smoke.md` for the other two empirical promises.

## Reproduce

```bash
export GROQ_API_KEY=...
export ANTHROPIC_API_KEY=...    # optional, opt-in only
python scripts/eval/latency_benchmark.py
```
