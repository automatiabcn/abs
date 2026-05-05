# Founder Test Fix Round 1 — Closeout

**Date:** 2026-05-05
**Branch:** `feat/sprint-q12-deep-quality` (HEAD 4b4dd92 + this round)
**Scope:** 3 founder-reported bugs + 13-page title sweep, frontend-only.

## Bugs closed

### BUG-2 HIGH — `/admin/marketplace` 30s timeout
**Root cause:** `MarketplacePanel.tsx` (and 2 sibling workflow components)
barrel-imported `@phosphor-icons/react`. In Next 15 dev mode the barrel pulled
the entire icon library into the route's first compile — 8191 modules / 21.2s.

**Fix:** `core/landing/next.config.ts` —
`experimental.optimizePackageImports: ['@phosphor-icons/react','lucide-react','framer-motion']`.
The flag rewrites named imports to deep entry points so dev only pulls what
the route uses. All three libs are side-effect-free.

**Result (cold compile, fresh Next dev):**
- before: 8191 modules / 21.2s, GET 22676ms
- after:  1682 modules / 1.17s, GET 1431ms
- Playwright `goto({ timeout: 5_000 })` warm-second: < 5s ✅

### BUG-1 HIGH — `/login` form did not redirect
**Root cause:** Form `onSubmit` ran a fetch + `window.location.href = …`,
but Playwright (and a fast human) clicked the submit button before React
hydrated the page. Without the React handler attached the browser fell back
to a native GET on the form — landing on `/login?` and never on `/panel`.

**Fix:** `core/landing/app/login/page.tsx` —
1. Track `hydrated` via a `useEffect` that flips after mount.
2. Disable submit button until `hydrated === true`.
3. After successful POST, call `router.push(dest)` (App Router) +
   `router.refresh()` for the RSC layout, with a 150ms `window.location.assign`
   fallback in case the router transition is a no-op.
4. `<form noValidate data-hydrated="…">` so tests can wait for the hydrated
   state explicitly.

**Result:** Playwright spec hits `/panel` within 4.6s end-to-end.

### BUG-3 MED — chat send button accessibility
**Surface:** `core/landing/components/chat/index.tsx`
**Fix:** Send button now exposes
- `aria-label="Mesaj gönder · Send message · Enviar"` (TR/EN/ES)
- `data-testid="chat-send"`
Plus matching `data-testid="chat-abort"` and trilingual `aria-label` on
the streaming Stop button.

### SWEEP — 14 panel/admin pages with unique `<title>`
**Before:** 13 of 14 routes inherited the landing root title
`Automatia ABS — Self-hosted AI ağı`. Only `/admin/workflow-builder`
shipped its own.

**Fix:**
- `app/panel/page.tsx`, `app/admin/audit/page.tsx`, `app/admin/users/page.tsx`,
  `app/admin/workflow-builder/page.tsx` (already had one — normalized
  format and added `Metadata` type annotation): added
  `export const metadata: Metadata = { title: …, robots: …}`.
- 11 client routes: added a sibling server-component `layout.tsx` whose
  only job is to export `metadata.title`. No UI is added — the parent
  `/panel/layout.tsx` and `/admin/layout.tsx` still own the chrome.

Format: `<H1> — ABS Panel · Automatia ABS` (or `… — ABS Admin · Automatia ABS`).

## Test deltas

- Added `core/landing/__tests__/playwright/founder-test-fix-1.spec.ts` —
  18 tests covering all four fix areas.
- All 18 pass in 16.9s on `--project=chromium-desktop`.

## Verification

| Gate | Result |
| ---- | ------ |
| `pytest --no-header -q` (3 ignores) | **1755 passed, 14 skipped, 3 deselected, 0 fail / 0 error** in 181.7s |
| Playwright `founder-test-fix-1.spec.ts` | **18 / 18 passed** in 16.9s |
| Marketplace cold compile (Next dev) | 1682 modules / 1.17s (was 8191 / 21.2s) |
| Image rebuild | **N/A — backend untouched this round** |

`pytest_full_suite: 1755 / 0 fail / 0 error`

## Files changed

```
core/landing/next.config.ts                                     (+12)
core/landing/app/login/page.tsx                                 (+~40, -2)
core/landing/components/chat/index.tsx                          (+4, -2)
core/landing/app/panel/page.tsx                                 (+10)
core/landing/app/admin/audit/page.tsx                           (+8)
core/landing/app/admin/users/page.tsx                           (+8)
core/landing/app/admin/workflow-builder/page.tsx                (+1, ~3)
core/landing/app/panel/{chat,tools,quota,meetings,transcription}/layout.tsx     (5 new)
core/landing/app/admin/{settings,providers,marketplace,pipelines,rag,graph}/layout.tsx (6 new)
core/landing/__tests__/playwright/founder-test-fix-1.spec.ts    (new, 18 tests)
artifacts/founder_test_fix_1/round_1.md                          (this file)
```

## Hand-off to founder

- Founder can re-run `/private/tmp/founder_feature_test.js` headed; expected:
  - PHASE A login redirect → `/panel` ✅
  - All 14 page visits succeed within `goto` budget; `/admin/marketplace` < 5s ✅
  - Chat send button discoverable via `[data-testid="chat-send"]` ✅
  - Each page's window title is unique (no more 13× landing title) ✅
- No backend changes — no docker rebuild required.
- No mutations to L21 / Mutmut / DR drill (founder-gated).
