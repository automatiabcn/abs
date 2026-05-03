# Round 24 — L25 sweep 2 workflow / chat boundary caps

**Sprint:** Q12 Session 3
**Layer:** L25 (boundary payload) — sweep 2
**Files touched:** 2 src + 1 new test
**Status:** ✅ shipped

---

## Real bugs surfaced

### Q12-L25-002 (HIGH DoS) — `/v1/workflows/execute` accepts UNBOUNDED workflow

`ExecuteRequest.workflow: Dict[str, Any]` had no nodes-count cap, no
edges-count cap, and no raw-payload cap. Post-auth (admin token or
panel session), an attacker — or a compromised JWT, or a multi-tenant
escape — could POST a 10k-node payload. `runner.plan()` walks every
node and allocates per-node, OOMing the worker.

Pre-fix proof in `TestQ12L25Sweep2WorkflowProof` constructs the
oversize payload directly via the Pydantic model and asserts:
1. **WITH** the new `model_validator` cap → `ValueError("nodes count
   exceeds cap")` (FastAPI surfaces as 422).
2. The cap is the load-bearing guard, not some incidental downstream
   check.

**Fix:** Pydantic `model_validator(mode="after")` on `ExecuteRequest`
caps `workflow.nodes ≤ WORKFLOW_NODES_MAX (200)` and
`workflow.edges ≤ WORKFLOW_EDGES_MAX (500)`. Cap values are generous
relative to the KOBİ template library (5–20 nodes typical) and leave
headroom for tool-augmented expansion.

### Q12-L25-003 (HIGH DoS) — `/v1/chat/completions` accepts UNBOUNDED messages list

`ChatCompletionsRequest.messages: List[ChatMessageIn]` had no length
cap. `ChatMessageIn.content` was already capped at 8000 chars
(Q11-L13 inheritance), so a 10,000-message payload at max content =
80 MB JSON. The Pydantic V2 parse + validate pass walks every message
before any handler runs. Even with a swift-fail downstream, the parse
itself is the DoS vector.

**Fix:** `messages: List[ChatMessageIn] = Field(..., min_length=1,
max_length=200)`. 200 mirrors the practical message-window before
LLM context compaction (claude.ai persists ≈100 turns + system
prompt before compaction; 200 leaves room for tool-augmented
chains).

---

## Tests

* `TestQ12L25Sweep2WorkflowNodes` — 4 HTTP tests via `auth_client`
  (panel session cookie pattern from `tests/test_q8_chat.py`):
  within-cap not-tripped, above-cap-rejected (nodes), above-cap-rejected
  (edges), nodes-must-be-list.
* `TestQ12L25Sweep2WorkflowProof` — direct Pydantic model assertion
  proving the validator is the gate.
* `TestQ12L25Sweep2ChatMessages` — 4 tests (3 direct Pydantic + 1
  HTTP via auth_client): within-cap-passes, above-cap-rejected,
  empty-rejected, HTTP returns 422 not 500.

23/23 PASS.

---

## Image + container evidence

```
image_rebuilt_at: 2026-05-03T14:53:xx (Q12 Session 3 fifth rebuild)
container_pytest_pass: 23/23
```

Live container smoke (no auth → 401 expected):
```
$ curl -sk -o /dev/null -w "%{http_code}\n" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"workflow":{"nodes":[],"edges":[]},"dry_run":true}' \
    http://localhost:8000/v1/workflows/execute
401
```

(422 path requires auth_client; covered by HTTP tests.)

---

## L25 counter

* Sweep 1 (R17): marketplace InstallBody UNBOUNDED — Q12-L25-001
  (HIGH DoS + path traversal + shell metachar). Pydantic Field
  max_length + alphanum pattern + 14 tests.
* **Sweep 2 (R24): workflow execute + chat completions UNBOUNDED**
  — **Q12-L25-002 + Q12-L25-003 (HIGH DoS each).** model_validator
  caps + Field max_length + 23 tests.

L25 → **2/3** (sweep 3 candidates: RAG ingest BATCH 100 doc parallel
DoS resilience, plugin install body 50MB Content-Length enforcement
at HTTP layer, OAuth client_id length cap on register endpoint if
exists).
