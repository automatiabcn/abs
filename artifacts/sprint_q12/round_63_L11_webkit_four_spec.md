# Q12 Session 8 — Round 63

**Layer:** Q11-L11 cross-browser (webkit-desktop)
**Specs:** `q12-l20-chaos-multi.spec.ts` + `q12-l26-long-running.spec.ts` + `q10-l4-aria-live-deep.spec.ts` + `q12-l18-cold-cache.spec.ts`
**Goal:** Validate the same four spec set against webkit that S7 R47/R48 + S8 R57/R62 covered on chromium and firefox.

## Result

**23 passed, 1 gated skip, 0 failed** in 1.8 min.

| Spec | webkit-desktop |
|------|----------------|
| `q12-l20-chaos-multi.spec.ts` | 3/3 PASS (scenarios 6, 7, 8) |
| `q12-l26-long-running.spec.ts` | 1 smoke PASS, 1 cookie persistence PASS, 1 gated 30-min skipped |
| `q10-l4-aria-live-deep.spec.ts` | 5/5 PASS (after R63 fix) |
| `q12-l18-cold-cache.spec.ts` | 13/13 PASS — all under budget; LCP table below |

## Real bug closed: **Q12-L11-WK-001 (MED cross-browser portability)**

First-pass run had 3 webkit-only failures, all in `q10-l4-aria-live-deep.spec.ts`:

1. scenario 1: sessions-list 503 → `sessions-error-tile` not visible
2. scenario 2: chat 503 → `chat-error-tile` not visible
3. scenario 4: `/panel` cascade-503 → `<p role="alert">yüklenemedi</p>` not visible

Page-snapshot evidence (scenario 1): the chat surface rendered with **real seeded sessions** ("mixed probe 0", "multi-503 cascade probe", "aria-live capture probe", "chaos probe 5 redirect") — that is, the `/v1/chat/sessions` request returned the actual backend payload, not the injected `503 {"detail":"down"}`. Reproduced under chromium baseline: original 503 was honoured. So the route inject works in chromium and firefox but not in webkit.

### Root cause

`/panel/chat` mounts `<ServiceWorkerRegister>` (S6 R36). The SW excludes `/v1/*` from its cache strategy but its fetch handler still wraps the request in `event.respondWith(fetch(req))`. In Chromium (Playwright 1.59) and Firefox 151 this passthrough is **transparent** to `page.route()`. In WebKit 26 (Safari 17 / Playwright 1.59) requests dispatched from the SW thread are not always visible to the route interceptor — confirmed by the page snapshot above.

### Fix

`test.use({ serviceWorkers: "block" })` at file level in `q10-l4-aria-live-deep.spec.ts`. These scenarios test error-tile mounting on `isError`, not SW behaviour, so blocking SW is the right scope. Cross-browser verification:

- **chromium-desktop** 5/5 PASS
- **chromium-mobile** 5/5 PASS
- **firefox-desktop** 5/5 PASS
- **webkit-desktop** 5/5 PASS

= **15/15 PASS across 4 browser projects after R63 fix** (was 12/15 PASS pre-fix because of webkit silent passthrough).

The other three specs (`chaos-multi`, `long-running`, `cold-cache`) already had the right scope. `cold-cache` already configured `serviceWorkers: "block"` per-context. `chaos-multi` uses the same `page.route()` pattern but on `/panel` root — webkit there does intercept because the SW only mounts after `/panel/chat` navigation, not on the panel root layout.

## Cold-cache LCP table (webkit-desktop)

```
/                       LCP=378ms   FCP=342ms   TTFB=273ms   budget=3500ms
/pricing                LCP=848ms   FCP=818ms   TTFB=691ms   budget=3500ms
/showcase               LCP=140ms   FCP=140ms   TTFB=99ms    budget=3500ms
/onboarding             LCP=354ms   FCP=104ms   TTFB=71ms    budget=3500ms
/panel                  LCP=447ms   FCP=102ms   TTFB=52ms    budget=4500ms
/panel/chat             LCP=727ms   FCP=125ms   TTFB=67ms    budget=5500ms
/panel/tools            LCP=448ms   FCP=110ms   TTFB=69ms    budget=5500ms
/panel/quota            LCP=106ms   FCP=106ms   TTFB=63ms    budget=4500ms
/panel/meetings         LCP=151ms   FCP=151ms   TTFB=92ms    budget=4500ms
/panel/transcription    LCP=138ms   FCP=138ms   TTFB=91ms    budget=4500ms
/admin/marketplace      LCP=367ms   FCP=108ms   TTFB=70ms    budget=4500ms
/admin/providers        LCP=402ms   FCP=105ms   TTFB=68ms    budget=4500ms
/admin/workflow-builder LCP=114ms   FCP=114ms   TTFB=68ms    budget=5500ms
```

(WebKit on macOS is faster than firefox-desktop dev-mode here because Apple's
network stack does not pay the firefox first-compile + heavy DevTools cost.)

## Layer state delta

- Q11-L11 cross-browser **webkit-desktop**: 4 spec PASS = full parity with chromium-desktop + chromium-mobile + firefox-desktop on the consolidated 4-spec set.
- Aria-live `q10-l4-aria-live-deep.spec.ts` now SW-blocked (rationale comment in source) — matches the cold-cache spec's pre-existing pattern.

## Image rebuild

Backend untouched — no rebuild. socat sidecar from R62 still up (verified `localhost:8000/healthz` 200 during this round).

## Diff

```
M  core/landing/__tests__/playwright/q10-l4-aria-live-deep.spec.ts  (+13 lines: test.use serviceWorkers:block + comment)
A  artifacts/sprint_q12/round_63_L11_webkit_four_spec.md
M  artifacts/sprint_q12/master_audit_summary.md
```
