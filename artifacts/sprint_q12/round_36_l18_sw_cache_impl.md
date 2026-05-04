# Round 36 — L18 Service Worker cache (3 strategies)

**Sprint:** Q12 Session 6
**Layer:** L18 (cold-cache LCP / offline resilience)
**Files touched:** 3 new + 1 edit
**Status:** ✅ shipped — 5/5 SW spec PASS, no regression on multi-failure chaos

---

## Brief

S5 deferred the L18 Service Worker cache implementation as
non-trivial frontend work. R36 ships a vanilla SW (no Workbox
dependency) with three route-group strategies + an exclusion list.

## Files

### `core/landing/public/sw.js` (NEW)

Vanilla SW, ~110 lines, three strategies:

| Route prefix | Strategy | Why |
|--------------|----------|-----|
| `/panel/chat*` | cache-first | Offline draft persistence — chat shell visible even when offline. |
| `/panel/dashboard*` or `/panel`, `/panel/` | network-first (3 s timeout → cache) | Dashboard shows real-time KPIs; cache only as a fallback when network is slow. |
| `/panel/rag*` | stale-while-revalidate | RAG admin views are not real-time critical; cache hit is good enough while background updates. |

Always pass-through:
- `/v1/*` (cascade chaos must surface, never cache 503/200)
- `/_next/*` (versioned-by-hash dev/build chunks)
- `/auth/*` (credentials)
- non-GET methods (POST/PUT/PATCH/DELETE)

Lifecycle: `install → skipWaiting()`, `activate → claim + clean
old caches`. Cache name versioned: `abs-panel-cache-v1`.

### `core/landing/components/panel/ServiceWorkerRegister.tsx` (NEW)

Client component that registers `/sw.js` on mount under `/panel/*`.
Bails on `process.env.NEXT_PUBLIC_DISABLE_SW === "1"` so chaos
tests can opt out via env. Failures are silent (non-fatal).

### `core/landing/app/panel/layout.tsx` (EDIT)

Mount `<ServiceWorkerRegister />` inside `<QueryProvider>` so it
runs once for the whole panel surface and never on the marketing
landing routes.

### `core/landing/__tests__/playwright/q12-l18-sw-cache.spec.ts` (NEW)

5 static + dynamic assertions:

1. `/sw.js` reachable, contains `abs-panel-cache-v1` + 3 route prefixes
2. Exclusion list contains `/v1/`, `/_next/`, `/auth/` + non-GET filter
3. 3 strategy fns present + correctly dispatched (chat→cacheFirst,
   rag→SWR, dashboard→networkFirst)
4. NETWORK_TIMEOUT_MS = 3000 (network-first fallback)
5. `<ServiceWorkerRegister />` mounted in panel/layout.tsx

---

## Verification

### SW spec

```
✓ sw.js shipped + version marker (358ms)
✓ exclusion list (/v1, /_next, /auth) (111ms)
✓ 3 strategy functions + dispatch (2ms)
✓ network-first 3s timeout (0ms)
✓ ServiceWorkerRegister mounts in panel layout (2ms)

5 passed (1.9s)
```

### Multi-failure chaos regression (SW must not break the
sessions-error-tile path from R35)

```
✓ scenario 6 cascade 503 (1.8s)
✓ scenario 7 mixed 429/503/abort (2.5s)
✓ scenario 8 all-5xx navigable (4.2s)

3 passed (9.2s)
```

The SW deliberately does not intercept `/v1/*`, so cascade 503 is
still surfaced via the new sessions-error-tile from R35.

---

## Image rebuild

N/A — frontend-only change. Backend not touched. Backend pytest
unchanged at 1630 PASS.

---

## Layer matrix delta

| Layer | Before R36 | After R36 |
|-------|------------|-----------|
| L18 | 3/3 ⭐ (SW deferred to Sprint 22) | **3/3 ⭐ deep** — SW shipped + 5 verifying tests, S5 defer reason closed |

---

## Counters

- Backend pytest: unchanged 1630 PASS / 14 skipped.
- Playwright: **+5 new tests** (q12-l18-sw-cache.spec.ts).
- Total Playwright in S6 so far: +5 (chaos multi upgrades count
  as test count: 0 since same number of tests, but failures
  flipped to passes).
- Atomic commits in round: 1.
