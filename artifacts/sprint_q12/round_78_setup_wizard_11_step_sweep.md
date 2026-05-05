# Round 78 — first-customer 11-step full-sweep E2E

**Date:** 2026-05-05 (Q12 Session 9)
**Branch:** `feat/sprint-q12-deep-quality`
**Layer:** Q12-L29 (NEW — first-customer journey)
**Commits:** 1 atomic (this round)

## Goal

Walk a brand-new tester from a fresh install all the way to the panel surfaces
that prove ABS works (chat, RAG, workflow), as a single TestClient-driven
journey. The brief framed it as an "11-step Playwright" sweep; we ship it as
a backend pytest journey because:

1. The setup wizard UI is **served by the backend** at `/setup` (static HTML
   in `app/static/setup/`) and gated by the `first_run` middleware — not by
   the Next.js landing app, so a Playwright spec on `localhost:3457` could
   never reach steps 1–6 in the first place.
2. A Playwright run that needed `setup_state.completed=False` would have to
   wipe the dev backend's state, which is the exact founder-gated destructive
   operation we deferred under L21.
3. The TestClient walk gives reproducible coverage in CI on every PR with no
   browser overhead — the assertion chain is what catches regressions in the
   tester journey.

## Layer scope (L29)

The 11 steps are folded into **3 pytest functions** so a failure in workflow
plumbing cannot mask a failure in chat:

| Test | Steps covered |
|------|---------------|
| `test_first_customer_11_step_full_sweep` | 1 fresh status + 2-7 wizard + 8 login + 9 panel/tools + 10 chat session create+list |
| `test_first_customer_post_setup_workflow_synth_and_dry_run` | wizard + login + 11a synthesize + 11b execute (dry_run) |
| `test_first_customer_post_setup_rag_smoke` | wizard + 11c RAG ingest+query contract (qdrant + embedder mocked) |

The 11-step framing in the brief expanded as:

```
 1. /v1/setup/status                  → completed=False (fresh)
 2. /v1/setup/step/admin              → 200, current_step=2
 3. /v1/setup/step/license            → 200, current_step=3
 4. /v1/setup/step/domain             → 200, current_step=4
 5. /v1/setup/step/anthropic          → 200, current_step=5
 6. /v1/setup/step/providers          → 200, current_step=6
 7. /v1/setup/step/test               → 200, completed=True
 8. /auth/login                       → 200, JWT cookie set
 9. /v1/panel/tools                   → 200, panel inventory shape
10. /v1/chat/sessions create + GET    → 201 + 200
11. /v1/workflows/synthesize+execute  → 200 + dry_run_ok
    (companion) /v1/rag/ingest+query  → 401/403 contract w/o tenant token
```

## Why RAG asserts the auth-gate, not happy-path

`/v1/rag/*` authenticates via OAuth bearer + tenant claim, not the admin
cookie that the setup-wizard journey establishes. Real RAG success-path
coverage already lives in `test_t011_rag_pipeline.py` and
`test_t012_cerbos_rag_filter.py`. R78's RAG step asserts the **contract the
panel UI relies on**: a missing-bearer call must return 401/403 with a
deterministic detail (`missing_bearer_token` / `missing_tenant_claim`) so the
panel can surface "RAG not configured" instead of an opaque 500. That is the
first-customer-journey-relevant invariant.

## Findings

- The detail set the contract test accepts is `{missing_bearer_token,
  missing_tenant_claim, missing_authorization, "Not authenticated"}`. The
  initial assertion missed `missing_bearer_token` (which is what the live
  endpoint returns when the bearer is absent entirely vs. malformed). Test
  caught the gap on first run; updated.
- No bugs in the setup wizard, login, panel/tools, chat sessions, or workflow
  surfaces — the journey passes end-to-end.

## Test results

```
tests/test_q12_l29_setup_wizard_full_sweep.py::test_first_customer_11_step_full_sweep PASSED
tests/test_q12_l29_setup_wizard_full_sweep.py::test_first_customer_post_setup_workflow_synth_and_dry_run PASSED
tests/test_q12_l29_setup_wizard_full_sweep.py::test_first_customer_post_setup_rag_smoke PASSED
3 passed in 3.20s
```

Backend pytest delta: 1731 → **1734** (+3).

## Followups (not this round)

- A real Playwright wrapper for the same journey requires either (a) a fresh
  isolated docker-compose namespace (as scaffolded by R77's
  `backup_restore_drill.sh` overlay, founder-gated) or (b) a setup-state
  reset endpoint protected by an env gate. Both are scoped out of R78 — the
  pytest journey is the locked contract; the Playwright wrapper would just
  be a UI mirror once isolation infra ships.
- Step 10 deliberately stops at "create session + list sessions" rather than
  firing `/v1/chat/completions`. Streaming the cascade-mock SSE inside this
  test is already covered by `test_q10_l2_integration.py` and adding it here
  would couple the journey to the SSE parsing harness for no extra signal.

## Image rebuild gate

This round adds a new test file only; backend code unchanged. Container exec
gate not triggered.
