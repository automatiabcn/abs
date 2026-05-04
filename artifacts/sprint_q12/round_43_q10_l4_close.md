# Round 43 — Q10-L4 aria-live deep CLOSED — 5/5 PASS

**Sprint:** Q12 Session 7
**Layer:** Q10-L4 (a11y) — deep CLOSED
**Files touched:** 2 edits (CheckoutButton + spec)
**Status:** ✅ shipped — 5/5 PASS

---

## Brief

S6 R40 shipped 4/5 PASS + 1 build-conditional skip on the
pricing CheckoutButton scenario. R43 closes the gap.

## Investigation

Initial fix path was to add `data-test="checkout-button"` to
`CheckoutButton.tsx` and let scenario 4 hit `/pricing`. Walking
through this:

1. **CheckoutButton is dead code.** Grep found exactly **one**
   import: `core/landing/__tests__/CheckoutButton.test.tsx`. No
   route renders it. `/pricing/page.tsx` is a 6-line redirect to
   `/#contact` — the pricing UI was retired in an earlier
   sprint.
2. So a `[data-test='checkout-button']` selector on `/pricing`
   will never find anything in the live build.

Pivot: change scenario 4 to a **real, currently-rendered**
aria-live surface — the `/panel` root error banner that mounts
`<p role="alert">Bazı veriler yüklenemedi …</p>` when any of
`tools.isError || quota.isError || cascade.isError`. Mock all
three to 503 and assert the banner becomes visible.

The `data-test` addition to CheckoutButton is kept as defensive
future-proofing — when CheckoutButton is reintroduced on a real
route, the SR contract will already be testable.

## Hygiene incident — stale React Client Manifest

Mid-investigation, /panel/transcription returned **HTTP 500**
with the dev-server error:

> Could not find the module `core/landing/components/panel/ServiceWorkerRegister.tsx#default`
> in the React Client Manifest.

This is the same dev-server stale-manifest class as R35 (T-Q02
echo). The ServiceWorkerRegister.tsx file (R36) exists on disk
but the running dev server's manifest is out of date.

Fix: `kill -9` the dev server, `rm -rf .next/`, restart `next dev`.
Manifest rebuilds cleanly; route returns 200.

This is a **dev-only** bug. R42 SW runtime spec ran clean
yesterday against the same source. Production builds (`next build`)
generate the manifest from scratch. Filed as a hygiene note, not
a layered defect — same class as T-Q02.

## Files

### `core/landing/components/CheckoutButton.tsx` (EDIT)

```tsx
<button
  type="button"
  data-test="checkout-button"
  data-tier={tier}
  ...
>
```

### `core/landing/__tests__/playwright/q10-l4-aria-live-deep.spec.ts` (EDIT)

- Scenario 3: `domcontentloaded` → `load` (transcription page is
  client-rendered; aria-live span mounts after JS loads), timeout
  raised 8 s → 12 s
- Scenario 4: rewritten — `/panel` with three mocked 503s
  (`/v1/system/quota_status` + `/v1/cascade` + `/v1/tools`)
  surfaces the page-level role=alert banner

## Verification

```
$ npx playwright test __tests__/playwright/q10-l4-aria-live-deep.spec.ts \
    --workers=1 --project=chromium-desktop

  ✓ scenario 1: sessions-list 503 (R35 pin) (4.6s)
  ✓ scenario 2: chat 503 chat-error-tile (1.7s)
  ✓ scenario 3: transcription aria-live polite (598ms)
  ✓ scenario 4: /panel root role=alert on multi-503 (4.4s)
  ✓ scenario 5: announcement log infrastructure (1.1s)

  5 passed (13.2s)
```

## Image rebuild

N/A — frontend test-only round + dev-server restart for stale-
manifest cleanup. Backend `app/` source untouched. Backend pytest
unchanged at 1633.

## Layer matrix delta

| Layer | Before R43 | After R43 |
|-------|------------|-----------|
| Q10-L4 | ⭐ FULL CLEAN deep (R40 4/5 + 1 build-conditional skip) | **⭐ FULL CLEAN deep CLOSED** (R43 5/5 PASS) |

## Counters

- Backend pytest: unchanged 1633.
- Playwright: **+0 new tests** (1 scenario rewritten, S6 skip closed).
- Atomic commits in round: 1.
