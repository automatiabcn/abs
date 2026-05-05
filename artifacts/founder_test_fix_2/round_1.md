# Founder Tester Fix — Round 2 / Round-1 (BUG-4 cascade live wiring)

## Verification

```
pytest_full_suite: 1760 passed / 0 fail / 0 error / 14 skipped / 3 deselected
image_rebuilt_at: 2026-05-05T18:18:00Z
live_path_verified: true
```

Baseline 1755 → 1760 (+5 new cascade live tests in
`tests/test_q12_cascade_live_wiring.py`). The 7-scenario provider degradation
matrix was updated to mock the orchestrator now that `/v1/cascade/run` walks
the live chain; the R91 final-acceptance test now accepts 502
`all_providers_failed` as the expected gate-failure surface (alongside the
pre-existing 503 `no_providers_configured`).

## Live curl evidence (after image rebuild)

```bash
$ curl -sk -b /tmp/cookie.txt http://localhost:8000/v1/cascade/providers
{"active":["anthropic","groq","cerebras","gemini","cohere"],
 "missing":["cloudflare"],"configured_count":5,"total":6,
 "anthropic_mock_mode":"off"}

$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/cascade/run \
    -d '{"prompt":"Türkiye başkenti nedir? Tek cümle yanıt ver."}'
{"completion":"Türkiye'nin başkenti Ankara'dır.",
 "provider":"anthropic","fallback_chain":["anthropic"],
 "tokens_used":45,"mock":false,"cached":false,
 "elapsed_ms":773,"model":"claude-haiku-4-5-20251001"}

$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/cascade/run \
    -d '{"prompt":"Tek cümle: Python listcomp nedir?","prefer":"groq"}'
{"completion":"Python listcomp, …",
 "provider":"groq","fallback_chain":["groq"],
 "tokens_used":94,"mock":false,"cached":false,
 "elapsed_ms":266,"model":"llama-3.1-8b-instant"}

# Cache hit (second identical call)
first:  HTTP 200 0.261s   (cached:false)
second: HTTP 200 0.013s   (cached:true)   ← 20× speedup
```

## Code change

* `app/api/cascade.py` — replaced the `503 live_cascade_pending` stub
  (lines 129-135) with `call_with_cascade(prompt, primary, fallbacks,
  model, use_cache, max_tokens)`. ProviderError → `502
  all_providers_failed`. Response surfaces `cached`, `elapsed_ms`,
  `model` fields.
* `app/providers/registry.py` — registered `AnthropicProvider` +
  `CohereProvider` so the live chain can reach them (gated by their
  own enable flags + key checks).

## Tests

* `tests/test_q12_cascade_live_wiring.py` (new, 5 cases):
  happy-path 200 + first provider, all-providers-fail → 502, prefer
  routing, cached-flag passthrough, empty chain → 503.
* `tests/test_q12_provider_degradation_matrix.py` — orchestrator
  mocked; assertions now expect 200 when ≥1 provider configured.
* `tests/test_q12_r91_final_acceptance.py` — Phase-2 detail check
  accepts `all_providers_failed` (502) or `no_providers_configured`
  (503) instead of the deleted `live_cascade_pending` (503).

## Bug status

* BUG-4 `/v1/cascade/run` live wiring → **DONE** (closed Q4 P7-live).

## Next

Round 2 = BUG-5 `/v1/workflows/synthesize` LLM-first + template fallback.
