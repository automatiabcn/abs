# Founder Tester Fix — Round 2 / Round-3 (BUG-6 RAG cookie session)

## Verification

```
pytest_full_suite: 1775 passed / 0 fail / 0 error / 10 skipped / 3 deselected
image_rebuilt_at: 2026-05-05T19:02:00Z
live_path_verified: true
```

Baseline 1755 → 1775 (+20 vs baseline; 5 cascade Round 1 + 7 workflow LLM
Round 2 + 4 RAG cookie session Round 3 + 4 previously-skipped tests now
running because Qdrant is healthy in dev).

## Live curl evidence (after image rebuild + qdrant overlay)

```bash
# Admin cookie session, no Bearer header
$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/rag/ingest \
    -d '{"text":"ABS founder smoke test ...","filename":"smoke.txt"}'
{"doc_id":"e17263eb3a5fcb17","chunks":1,"tokens_estimated":38,
 "collection":"abs_documents","elapsed_ms":43.8}
HTTP 200

$ curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/rag/query \
    -d '{"query":"ABS founder cookie session","limit":3}'
{"query":"ABS founder cookie session",
 "hits":[{"chunk_id":"28adc664-3d63-5318-9cc6-c93302e18a9f",
          "score":0.13344681,
          "text":"ABS founder smoke test ...",
          "doc_id":"e17263eb3a5fcb17", "seq":0, …}],
 "elapsed_ms":13.8}
HTTP 200

# Anonymous (regression guard)
$ curl -sk -X POST http://localhost:8000/v1/rag/query \
    -d '{"query":"x","limit":1}'
{"detail":"missing_bearer_token"}
HTTP 401
```

## Code changes

* `app/api/v1/deps.py`:
  * Added `get_admin_or_bearer_auth_context` — Bearer JWT preferred,
    falls back to the panel `abs_session` cookie. Cookie path resolves
    the admin's tenant via `_resolve_tenant` and synthesises an
    `AuthContext` with `roles=["admin"]`. The original
    `get_auth_context` is unchanged so MCP gateway / hooks / audit-log
    routes keep their Bearer-only contract.
* `app/middleware/cerbos_rag_filter.py`:
  * `rag_action_dep` swapped from `get_auth_context` to
    `get_admin_or_bearer_auth_context`. RAG endpoints now accept either.
* `app/rag/pipeline_v10.py`:
  * Replaced the legacy `chunk_id = "<doc_id>-<seq:04d>"` (which Qdrant
    rejects with `is not a valid point ID`) with a deterministic
    UUID5 derived from `doc_id/seq`. Idempotent reruns; ID still
    inspectable from a known doc.
* `infra/docker-compose.dev.yml`:
  * `ABS_CERBOS_HOST: cerbos:3593` → `http://cerbos:3592`. The Python
    `cerbos.sdk.client` is HTTP and was crashing every PDP call with
    `Request protocol 'cerbos://'.` because the SDK parsed the
    schemeless gRPC port as a URI scheme.
* `infra/docker-compose.qdrant.yml`:
  * Healthcheck rewritten from `wget -qO- /readyz` (qdrant 1.17.1 ships
    without wget) to a Bash `/dev/tcp` socket open. Qdrant now reports
    healthy and the `depends_on: condition: service_healthy` chain
    can succeed.

## Tests

* `tests/test_q12_rag_cookie_session.py` (new, 4 cases):
  * Cookie session → 200 on `/v1/rag/query`.
  * Cookie session → 200 on `/v1/rag/ingest`.
  * No cookie + no Bearer → 401 missing_bearer_token.
  * Cookie + invalid Bearer → 401 (Bearer wins, malformed token errors out).
* `tests/test_q11_l13_hypothesis_deep.py`:
  * Added `_rag_stack_fakes` autouse fixture — the cookie fallback now
    unlocks the RAG route from the 1000-example hypothesis fuzz, so we
    stub the embedder + Qdrant to keep that loop hermetic. (The
    contract under test there is "no 5xx on input fuzz", not "vector
    search works"; 401 short-circuit is gone.)
* `tests/test_t011_rag_pipeline.py`:
  * `test_late_chunks_basic_count_and_ordering` updated to assert
    chunk_id matches `pipe._chunk_uuid(doc_id, seq)` (deterministic
    UUID5) and uniqueness across the chunk list.

## Bug status

* BUG-6 `/v1/rag/ingest` cookie session UX → **DONE**.
  * Two infra blockers found-and-fixed during live verification:
    * Cerbos host scheme drift in dev overlay.
    * Qdrant point-ID format never exercised by tests.

## Round 1+2+3 close-out

| Round | Bug | Endpoint | Status |
|------:|-----|----------|--------|
| 1 | BUG-4 | `/v1/cascade/run` | LIVE — Anthropic Claude 200 in 773ms |
| 2 | BUG-5 | `/v1/workflows/synthesize` | LIVE — `source: llm`, no template fallback in happy path |
| 3 | BUG-6 | `/v1/rag/{ingest,query}` | LIVE — cookie session works, semantic hit returned |

`pytest_full_suite: 1775 passed / 0 fail / 0 error` after all three rounds.

## Next

Round 4 = founder Playwright headed re-run. All 4 backend endpoints
exercised by the founder's session (cascade + workflow + chat + rag) now
have live evidence.
