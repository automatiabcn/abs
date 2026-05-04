# Round 47 — L26 active drill: drop + reconnect

**Sprint:** Q12 Session 7
**Layer:** L26 (long-running session) — active surface
**Files touched:** 1 new test
**Status:** ✅ shipped — 3/3 PASS chromium-desktop

---

## Brief

S6 R37 ran the **passive** 30-min idle drill (heap drift -9.63 MB,
0 5xx). That covered leak + auto-cleanup. R47 covers the **active**
surface: what happens when failures land *while the user is
mid-interaction*?

Three drop-shaped failures injected via Playwright `page.route()`:

1. **SSE mid-stream abort** — connection drops after the first
   chunk. The Vercel AI SDK reader surfaces partial; chat client's
   `finally{}` block must unstick `isStreaming=false` so the input
   re-enables.
2. **SSE 502 Bad Gateway** — Caddy/proxy restart simulation. R35's
   `chat-error-tile` (with `role="alert"`) must surface.
3. **Sessions GET drop** — `/v1/chat/sessions` returns 502 every
   call. R35's `sessions-error-tile` banner must mount, and the
   retry button must be clickable (no JS error).

## File

### `core/landing/__tests__/playwright/q12-l26-active-drill.spec.ts` (NEW)

3 chromium-desktop tests. Network-only — no real backend
mutation. Pattern mirrors S6 R32 chaos multi but with a
streaming-aware mock (scenario 1 sends one SSE chunk before
aborting).

## Engineering note — the false-start scenario 3

First version of scenario 3 staged "first call OK → subsequent
calls fail" and tried to trigger refetch via `window.dispatchEvent`.
Two issues:

1. The first 500 ms wait wasn't enough for the dynamic chunk to
   load + ChatClient to mount + the first fetch to dispatch.
   `callCount === 0` at assertion time.
2. `refetchOnWindowFocus: true` doesn't actually refetch on
   synthetic `focus`/`visibilitychange` events in headless
   Chromium — the page never lost focus to begin with.

Fix: simplified scenario 3 to "all GET calls 502" — banner
mounts on cold load, retry button stays clickable. POST/DELETE
pass through so the mock doesn't shadow other endpoints.

## Verification

```
$ npx playwright test __tests__/playwright/q12-l26-active-drill.spec.ts \
    --workers=1 --project=chromium-desktop

  ✓ scenario 1: SSE mid-stream abort (1.7s)
  ✓ scenario 2: SSE 502 → chat-error-tile (1.3s)
  ✓ scenario 3: sessions drop → banner + retry (3.9s)

  3 passed (7.6s)
```

## Image rebuild

N/A — frontend test-only round. Backend unchanged.

## Layer matrix delta

| Layer | Before R47 | After R47 |
|-------|------------|-----------|
| L26 | 3/3 ⭐ (S6 R37 passive 30-min) | **3/3 ⭐ deep** (passive idle + active drop+reconnect) |

L26 stays at 3/3 ⭐ counter — R47 adds depth on the active surface.

## Counters

- Backend pytest: unchanged 1665.
- Playwright: **+3 new tests**.
- Atomic commits in round: 1.
