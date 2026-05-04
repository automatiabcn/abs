# Round 65 — Sprint 22 RSC Phase B leg 2: `/admin/users` split-shell

**Layer:** Sprint 22 RSC migration (Q12 S8 brief HIGH #3)
**Status:** ✅ ship — split-shell live, 6/6 Playwright PASS across chromium + firefox + webkit
**Time:** 2026-05-04

## Goal

Mirror R64's pattern on `/admin/users`. The page is interactive (invite-dialog state, mutation, 60 s react-query refetch) so a full RSC swap is wrong; the right shape is server-fetch initial slice → client island for interactivity.

## What changed

| File | Kind | Note |
|------|------|------|
| `core/landing/app/admin/users/page.tsx` | rewrite | server component; awaits `cookies()`, fetches `/v1/admin/users` server-side with `abs_session` forwarded, falls back to MOCK_USERS on any failure, renders `<UsersClient initialUsers={...}>` |
| `core/landing/app/admin/users/UsersClient.tsx` | new | the previous whole-page client component verbatim, minus the MOCK fallback (now lives server-side); `useQuery` seeds from `initialData: initialUsers`; invite mutation + dialog state preserved |
| `core/landing/app/admin/users/types.ts` | new | shared `UserRow` interface + MOCK_USERS fixture so server and client agree on shape |
| `core/landing/__tests__/playwright/q12-r65-rsc-users-split-shell.spec.ts` | new | 2 scenarios × 3 browsers = **6/6 PASS** in 11.4 s |

## Smoke evidence

```
$ curl -sk -L -b /tmp/q12_cookie.txt http://localhost:3457/admin/users
code=200, html size 83 624 bytes

$ grep -oE 'data-test="user-row"' /tmp/users_page.html | wc -l
2          # rows already in HTML before any client refetch
$ grep -oE 'data-user-id="[0-9]+"' /tmp/users_page.html
data-user-id="2"
data-user-id="1"

$ for i in 1 2 3; do curl -sk -L -b /tmp/q12_cookie.txt \
    http://localhost:3457/admin/users -o /dev/null \
    -w "warm_${i} ttfb=%{time_starttransfer}s total=%{time_total}s\n"; done
warm_1 ttfb=0.104378s total=0.107124s
warm_2 ttfb=0.058584s total=0.061213s
warm_3 ttfb=0.052610s total=0.055434s
```

## Hydration race lesson (caught + handled in spec)

The first batched run had an interesting failure: clicking `[data-test="users-invite-open"]` then immediately asserting on `[data-test="users-invite-email"]` failed in 3-of-3 browsers when run in parallel with other Playwright workers. Run alone (one project) it passed in 875 ms. Cause: under dev-mode + parallel-worker contention, React 19 hydration finishes a beat after `waitUntil:"load"`. The click registered on the server-rendered DOM but the `Dialog` open-state setter (a client hook) wasn't yet bound, so the dialog never opened.

Fix in spec (not a product bug): `expect.poll()` retries the click against the dialog-visibility predicate with backoff `[100, 300, 600, 1200] ms`, total 8 s budget. This rides past the hydration race without hiding genuine breakage — if the island never hydrates, the poll exhausts.

This is a property of the spec, not the migration. Pre-R65 (whole-page client) had the same hydration delay; R65 doesn't make it worse. Worth recording for any future split-shell tests that interact within ~200 ms of `goto`.

## Cross-browser parity

```
[chromium-desktop] heading + invite trigger (poll retry)            ✓ 2.3s
[chromium-desktop] server initialData payload in HTML               ✓ 0.95s
[firefox-desktop]  heading + invite trigger (poll retry)            ✓ 9.5s
[firefox-desktop]  server initialData payload in HTML               ✓ 8.7s
[webkit-desktop]   heading + invite trigger (poll retry)            ✓ 2.5s
[webkit-desktop]   server initialData payload in HTML               ✓ 7.2s
6 passed (11.4s)
```

## What R65 does NOT do

- Lighthouse before/after measurement is R66.
- `/panel/dashboard` audit (the third candidate from R59) is R67+.

## Image rebuild gate

Backend untouched — no rebuild. Frontend dev (3457) reload picked up the new server component automatically; warm hits are 53–104 ms TTFB.

## Layer state delta

- Sprint 22 RSC Phase B leg 2: ✅ shipped.
- Sprint 22 RSC Phase B is now **2/2** routes migrated (audit + users).
- Q11-L11 cross-browser webkit: +1 spec (R65 split-shell) on top of R63 4-spec + R64 split-shell. Engine-agnostic across all four projects.
- No Q12 layer extension (Sprint 22 work).

## Diff summary

```
A  core/landing/app/admin/users/UsersClient.tsx                       (~250 lines, hot path of original page.tsx)
A  core/landing/app/admin/users/types.ts                              (~40 lines, shared shape)
M  core/landing/app/admin/users/page.tsx                              (rewrite, ~50 lines, server component)
A  core/landing/__tests__/playwright/q12-r65-rsc-users-split-shell.spec.ts  (~110 lines, 2 scenarios × 3 browsers = 6/6 PASS)
A  artifacts/sprint_22/round_65_rsc_admin_users_split_shell.md
M  artifacts/sprint_q12/master_audit_summary.md
```
