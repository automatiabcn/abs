# Cascade redundancy smoke

> Generated: 2026-08-04T09:17:44+00:00 · duration: 0.27s · `8/8` rounds green

Each round monkey-patches the provider registry: every provider in the chain is a stub that either returns `ok:<provider>` or raises a transient `ProviderError`. **No real API calls** — this is a contract smoke for the cascade orchestrator's fallthrough logic, executed against the production `app.cascade.orchestrator.call_with_cascade` code path.

Chain under test (paid-first): `anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere`.

## Rounds

| Killed | Chain | Expected answerer | Actual answerer | Elapsed (ms) | Pass |
|---|---|---|---|---|---|
| `—` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 151.73 | ✅ |
| `anthropic` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `openrouter` | `openrouter` | 1.05 | ✅ |
| `openrouter` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.62 | ✅ |
| `groq` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.56 | ✅ |
| `cerebras` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.53 | ✅ |
| `gemini` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.52 | ✅ |
| `cloudflare` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.5 | ✅ |
| `cohere` | anthropic → openrouter → groq → cerebras → gemini → cloudflare → cohere | `anthropic` | `anthropic` | 0.55 | ✅ |

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
