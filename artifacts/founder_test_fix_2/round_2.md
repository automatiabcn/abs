# Founder Tester Fix — Round 2 / Round-2 (BUG-5 workflow LLM synthesize)

## Verification

```
pytest_full_suite: 1767 passed / 0 fail / 0 error / 14 skipped / 3 deselected
image_rebuilt_at: 2026-05-05T18:31:00Z
live_path_verified: true
```

Baseline 1755 → 1767 (+12 vs baseline; 5 cascade Round 1 + 7 workflow LLM Round
2). New tests in `tests/test_q12_workflow_llm_synthesize.py` cover happy path,
template fallback, invalid-JSON retry-then-template, 3 locales (TR/EN/ES), and
the ABS_WORKFLOW_LLM_ENABLED=false opt-out.

## Live curl evidence (after image rebuild)

```bash
$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/workflows/synthesize \
    -d '{"intent":"Müşteri toplantı kaydı geldiğinde transcribe et + RAG ingest et + 3 madde Slack özet gönder.","locale":"tr"}'
HTTP 200
source: llm
explanation: LLM-synthesised workflow (revisions=0)
nodes_count: 4

$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/workflows/synthesize \
    -d '{"intent":"When a Stripe payment fails, send an alert to Slack and open a Linear ticket","locale":"en"}'
HTTP 200
source: llm
nodes: 2
first node: Send Slack alert
```

`source != "template"` on both calls — the 503 stub is gone, real cascade is
synthesising domain-aware workflows.

## Code change

* `app/api/workflows.py`:
  * Imported `call_with_cascade`, `get_active_providers`, `ProviderError`.
  * Replaced the old `_llm_synth_fn` (which always raised
    `llm_provider_not_wired`) with `_cascade_synth_fn`. The new function
    picks the first active provider via `get_active_providers()`, runs
    `call_with_cascade(prompt, primary, fallbacks, use_cache=True,
    max_tokens=2048)`, and surfaces empty/error responses as
    `SynthesisError` so the route's try/except still falls back to a
    keyword-matched template.
  * Default for `ABS_WORKFLOW_LLM_ENABLED` flipped from `false` → `true`.
    Operators who want the prior template-only behaviour can still
    explicitly opt out.
  * Explanation text re-flows: `"LLM-synthesised workflow (revisions=N)"`
    on success, or `"Template fallback after LLM failure: <reason>. <orig>"`
    on the graceful path.

## Tests

* `tests/test_q12_workflow_llm_synthesize.py` (new, 7 cases):
  * `test_llm_first_returns_source_llm` — happy path.
  * `test_template_fallback_when_cascade_unavailable` — `SynthesisError` →
    200 + source=template.
  * `test_invalid_llm_json_falls_back_to_template` — garbage JSON across
    every retry still 200.
  * `test_locale_variants_succeed[en/tr/es]` — three parametric cases,
    each asserts the prompt carries the locale tag and the response is
    valid.
  * `test_disabled_workflow_llm_uses_template` — env-var opt-out path.

## Bug status

* BUG-5 `/v1/workflows/synthesize` LLM bypass → **DONE**.

## Next

Round 3 = BUG-6 `/admin/rag` UI auto-token mint or cookie-from-cookie
tenant-default token so RAG ingest/query work without the operator pasting
a Bearer token by hand.
