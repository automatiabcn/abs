# Real Beta E2E Policy (T-R08)

The "real beta E2E" suite proves the journey a beta tenant takes through ABS.
It is an **acceptance gate** for the Sprint 18 close-out — Sprint 19 cannot
ship if either side of the suite is red.

## Scope

| Pillar | Tested | NOT tested |
|---|---|---|
| RAG ingest + tenant isolation | ✅ via `MeetingRAGIndexer` + fake store | live Qdrant cluster |
| Gmail integration (mock backend) | ✅ vault → list → draft → send → label | real Google OAuth round-trip (covered by T-Q03 respx tests) |
| Recall.ai integration (mock backend) | ✅ schedule + status + cost + tenant tag | real Recall.ai API (covered by T-Q03 respx tests) |
| Action items + ticket linking | ✅ extracted assignees match fixture expectations | linear/jira live API |
| UI journey through landing app | ✅ home → pricing → showcase → onboarding → beta → connect | screenshot diffing (deferred to a future visual-regression task) |
| **Stripe / billing** | ❌ **explicitly excluded** | beta tenants opt in without billing |

## Files

| Path | Purpose |
|---|---|
| `core/backend/tests/fixtures/acme_test_tenant.json` | The acme-test tenant fixture. RAG corpus, Gmail seed inbox, Recall meeting URL, expected acceptance values. |
| `core/backend/tests/e2e/test_real_beta_e2e.py` | 5 pytest cases: fixture shape, meeting round-trip, RAG-index isolation, Gmail full flow, Recall schedule. |
| `core/landing/__tests__/playwright/beta-e2e.spec.ts` | 3 Playwright cases: 6-route 15-min envelope walk, billing kill-switch sanity, onboarding progress-tracker shape. |

## Why mock backends, not live calls

- **CI determinism** — live Recall.ai charges per recording-hour; live Gmail
  needs a Google Cloud project + sandbox user. Both already have respx-mocked
  unit suites (T-Q03) that exercise the **`_GoogleBackend`** /
  **`_RecallBackend`** code paths. Re-running them in this E2E gives no new
  coverage; what we *do* gain here is the cross-module flow (vault ↔ MCP ↔
  rate limiter ↔ tenant isolation).
- **Stripe is excluded by design** — beta participants are invited at
  `NEXT_PUBLIC_BILLING_ENABLED=false`. The Playwright billing-kill-switch
  test asserts no `stripe.com` / `checkout` links render on `/pricing`
  during beta.

## Running locally

```bash
# Backend (acme-test tenant pipeline):
cd core/backend
.venv/bin/python -m pytest tests/e2e/test_real_beta_e2e.py -v

# UI (15-min envelope):
cd core/landing
npx playwright test beta-e2e.spec.ts --project=chromium-desktop
```

## CI wiring

The backend cases run inside the existing `pytest` job in
`.github/workflows/ci.yml` (no new job needed — `tests/e2e/` is already on
the collection path).

The Playwright cases run inside `.github/workflows/perf-budget.yml` →
`web-vitals` job which already boots `next dev` on port 3457. The job
discovers `__tests__/playwright/*.spec.ts` so `beta-e2e.spec.ts` is picked
up automatically.

## Acceptance criteria for closing T-R08

1. All 5 backend cases pass under `.venv/bin/python -m pytest`.
2. All 3 Playwright cases pass under `npx playwright test`.
3. No Stripe / checkout link appears anywhere in the journey.
4. Console error budget on the journey is **0** (excluding the documented
   ignore patterns: `Stripe`, `favicon`, `DevTools`, `WebSocket`).
5. Onboarding progress tracker exposes exactly 5 steps regardless of locale.

## Promoting from mock → live (post-GA)

When the founder approves real-customer engagement (Caveat #13 / #14):

1. Provision a sandbox Google Cloud project; mint an OAuth refresh token
   for `gmail.modify`. Drop it into the production vault (`app.vault.cache`),
   not the fixture JSON.
2. Subscribe to Recall.ai with the $50/day cost cap (`recall_ai_cost_cap_usd_per_day`).
3. Flip `ABS_GMAIL_BACKEND=google` and `ABS_RECALL_BACKEND=recall` per
   tenant via the helm umbrella values.
4. Re-run the backend suite with `--live` markers (to be added once the
   sandbox creds exist) — those cases will gate-skip until both env vars
   are set.

Until step 4 is done, this E2E remains **mock-backed**. That is a deliberate
choice; do not silently flip it without updating this policy first.
