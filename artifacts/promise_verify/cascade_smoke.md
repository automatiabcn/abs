# Cascade redundancy smoke

> Generated: 2026-07-14T11:48:51+00:00 · duration: 0.46s · `7/7` rounds green

Each round monkey-patches the provider registry: every provider in the chain is a stub that either returns `ok:<provider>` or raises a transient `ProviderError`. **No real API calls** — this is a contract smoke for the cascade orchestrator's fallthrough logic, executed against the production `app.cascade.orchestrator.call_with_cascade` code path.

Chain under test (paid-first): `anthropic → groq → cerebras → gemini → cloudflare → cohere`.

## Rounds

| Killed | Chain | Expected answerer | Actual answerer | Elapsed (ms) | Pass |
|---|---|---|---|---|---|
| `—` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 218.47 | ✅ |
| `anthropic` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `groq` | `groq` | 2.13 | ✅ |
| `groq` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 1.76 | ✅ |
| `cerebras` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 1.08 | ✅ |
| `gemini` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 1.09 | ✅ |
| `cloudflare` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 1.42 | ✅ |
| `cohere` | anthropic → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 1.98 | ✅ |

## Customer interpretation

If any one of the six providers becomes unavailable, the cascade falls through to the next configured provider on the same request. The customer never observes a hard 5xx unless **every** provider in the chain is simultaneously down — a scenario this smoke covers indirectly: zero remaining providers ⇒ `ProviderError` re-raised on the boundary, where the gateway returns 503 with the `configure-key` CTA.

## What this smoke does NOT prove

- It does not measure real provider latency under failure (see `latency_benchmark.md` for the live Groq/Anthropic numbers).
- It does not exercise rate-limit recovery (`429 + Retry-After`), circuit-breaker windows, or partial outages where one provider returns 5xx intermittently — those have dedicated tests in `test_cascade*.py`.
- It uses stub providers; quality of the answer is out of scope. PROMISE.md "What we do NOT claim" governs that.

## Reproduce

```bash
python scripts/eval/cascade_smoke.py
```
