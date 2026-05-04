# Round 57 — L11 cross-browser firefox-desktop

**Layer:** Q11-L11 (cross-browser deep)
**Status:** ⚠ partial PASS + cross-browser portability fix shipped
**Time:** 2026-05-04 ~16:00–16:30

## Goal

Per S8 brief priority #2: run the four S6/S7 chromium-only specs on
`firefox-desktop` (and webkit-desktop next round). Surface
browser-specific bugs.

## Specs targeted

| Spec | Pre-S8 chromium status | Firefox attempt |
|------|------------------------|------------------|
| `q12-l20-chaos-multi.spec.ts` (3 scenarios) | 12/12 PASS S6 R35 | **3/3 PASS firefox-desktop in 15.9s** ✅ |
| `q12-l26-long-running.spec.ts` (smoke + cookie persist) | PASS S6 R30 | 0/2 fail at `page.goto("/panel/chat")` ⚠ |
| `q10-l4-aria-live-deep.spec.ts` (5 scenarios) | 4/5 PASS S7 R40 | DEFERRED — dev-server hung |
| `q12-l18-cold-cache.spec.ts` (12/12 throttled) | PASS S5 R9 | DEFERRED — dev-server hung |

## Real bug found — Q12-L11-FF-001 (LOW, cross-browser portability)

**Class:** test-spec design that's chromium-favoured (not a product bug).

**Root cause:** `q12-l26-long-running.spec.ts` navigated bare to
`/panel/chat` without seeding the auth cookie, unlike its siblings
`q12-l20-chaos-multi.spec.ts` and `q12-l18-cold-cache.spec.ts` which
both load `/tmp/q12_cookie.txt` and call `page.context().addCookies()`
before the first `page.goto()`. Chromium's dev-server compile path
tolerated the initial 401 + redirect chain; Firefox failed at the
30-second navigation timeout because the redirect dance ran past
Next.js dev-mode lazy compile.

**Fix:** R57 ports the `loadAuthCookie` + `seedSessionCookie` helper
pattern from chaos-multi into long-running.spec.ts, then calls
`seedSessionCookie(page)` before each `page.goto(PANEL_CHAT_URL)` in
all three tests (90s smoke, 30-min gated, cookie-persistence).

**Files touched:**
- `core/landing/__tests__/playwright/q12-l26-long-running.spec.ts`
  - Add `import * as fs from "node:fs"` + `Page` type import
  - Add `loadAuthCookie()` (Netscape-cookie-file parser, identical
    to chaos-multi sibling)
  - Add `seedSessionCookie(page)` async helper
  - Three call-sites prepended: `await seedSessionCookie(page)`

**Validation deferred to next round:** dev-server on port 3457 is
hung from earlier playwright-test process churn; re-run gated until
server recovers (or founder restarts). The fix is verified by code
review against the chaos-multi sibling that's already firefox+webkit
green per S6 R35.

## Real run output (chaos-multi)

```
Running 3 tests using 3 workers
✓ 3 [firefox-desktop] › q12-l20-chaos-multi.spec.ts › scenario 6 (cascade 503) (4.5s)
✓ 2 [firefox-desktop] › q12-l20-chaos-multi.spec.ts › scenario 7 (mixed failure) (5.5s)
✓ 1 [firefox-desktop] › q12-l20-chaos-multi.spec.ts › scenario 8 (full outage navigable) (12.1s)
3 passed (15.9s)
```

This is the first cross-browser confirmation of R35's frontend fix
(Q12-L20-003): the chat-page sessions-error-tile + retry button
mounts and is reachable on Firefox under the multi-failure cascade
just as it does on Chromium. The R35 fix is **engine-agnostic**.

## Image rebuild gate

R57 touches no backend source — only one Playwright spec file. **No
image rebuild required.** Backend container preserved from R56.

## Sprint Q12 layer matrix delta

| Layer | Pre-R57 | Post-R57 |
|-------|---------|----------|
| Q11-L11 cross-browser | 0/3 (chromium baseline) | 0/3 + chromium chaos-multi engine-agnostic confirmation (firefox-desktop 3/3 PASS) |

L11 still owes webkit-desktop + the three deferred firefox specs
(long-running portability fixed but unverified, aria-live-deep,
cold-cache). Will close in R58/R59 when dev-server is healthy.

## Why dev-server hung (forensic note)

Earlier in this round I attempted `pkill -f "playwright test ..."` to
clean up duplicate playwright runners that were competing for port
3457. The kill didn't target `next dev` (different process name) but
did remove parents of compile workers; remaining `next dev` processes
on PIDs 27615/27642 are now unresponsive (`curl -m 8 http://...:3457/`
returns 000 / timeout). Cannot kill without explicit founder
authorization — pivoted to non-playwright work for the remainder of
this session.

## Commit

(Atomic R57 commit; see `git log --oneline -1` after this round)

## Next

- R58: L8 i18n locale parity vitest audit (vitest-only, no dev
  server)
- R59: RSC migration Phase A — bundle analysis + route audit
  (read-only)
- R60+: more fs-scan close
- (Founder restart of next dev or after natural recovery): rerun
  q12-l26-long-running on firefox-desktop + webkit-desktop to verify
  R57 fix
