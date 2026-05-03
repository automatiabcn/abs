# Round 32 — L20 round 4 multi-failure simultaneous chaos

**Sprint:** Q12 Session 5
**Layer:** L20 (chaos engineering) — round 4 deep
**Files touched:** 1 new Playwright spec
**Status:** ✅ shipped — 3 scenarios (1 PASS + 2 documented `test.fail()`)

---

## Real bug surfaced

### Q12-L20-003 (MED UX) — chat page hangs at "Yükleniyor…" under sessions-list 503

The single-failure chaos scenarios (q12-l20-chaos.spec.ts scenarios
1–5, all PASS) showed the chat page surfaces a `chat-error-tile`
when `/v1/chat/completions` fails. However, when **multiple chat
endpoints fail simultaneously** — specifically `/v1/chat/sessions`
along with `/v1/chat/completions` — the page renders only:

```
<paragraph>Yükleniyor…</paragraph>
```

…and never mounts an error indicator. Captured page snapshot from
the failing test trace:

```yaml
- main:
    - heading "Sohbet" [level=1]
    - paragraph: Yükleniyor…
```

No error tile, no retry CTA, no spinner-stop, no console assertion
of the network failure surface. The user has zero signal that the
sessions-list call failed — the page is indistinguishable from a
slow-but-healthy fetch.

**Root cause hypothesis:** the SessionsList container blocks any
downstream chat-error-tile mount on its own resolution. When the
sessions fetch hangs in error space without a fallback render, the
entire chat surface stays in the loading paragraph state.

**Fix surface (Sprint 22 frontend resilience pass):** SessionsList
must mount an error fallback (or analogous chat-error-tile) when
`/v1/chat/sessions` returns 5xx. Per ABS frontend convention,
`useSWR` error handler should surface a `chat-error-tile` data-test
selector for parity with the completions failure path.

---

## Test inventory

`core/landing/__tests__/playwright/q12-l20-chaos-multi.spec.ts` —
3 scenarios.

| # | Test | Multi-failure profile | Status |
|---|------|------------------------|--------|
| 6 | chat 503 + sessions 503 + quota 503 (cascade) | 3 simultaneous 503s | `test.fail()` — Q12-L20-003 |
| 7 | 429 + 503 + connection abort (mixed) | rotating fault per request + sessions 503 | `test.fail()` — Q12-L20-003 same root cause |
| 8 | ALL endpoints 5xx — page still navigable to /panel | total backend outage | ✅ PASS — frontend routing decoupled from backend |

The `test.fail()` pattern (mirror of R5's L20-001 redirect-loop)
ships the finding without blocking CI: Playwright treats an
expected-fail test as PASS in the suite total, which is the correct
behavior when the assertion is documenting a known bug awaiting
frontend fix.

---

## Verification

```
core/landing $ npx playwright test q12-l20-chaos-multi.spec.ts \
                 --project=chromium-desktop

Running 3 tests using 3 workers
  ✓ scenario 8: ALL endpoints 5xx — page still navigable to /panel (13.4s)
  ✘ scenario 6: chat 503 + sessions list 503 + completions 503 (cascade) (22.7s)
  ✘ scenario 7: 429 + 503 + connection abort (mixed failure modes) (24.7s)

  3 passed (25.4s)
```

Playwright counts `test.fail()` tests that DID fail as `passed`
because their failure was documented and expected. So all 3 land in
the green count from CI's perspective; only a future fix that makes
6/7 actually PASS would flip the marker on (the runner errors on a
no-longer-failing `test.fail`).

The scenario 8 PASS is itself an important positive: even with 100%
backend `/v1/*` outage the user can still navigate to `/panel` from
the chat surface without console-error explosion or white-screen.
This is the absolute minimum graceful contract.

---

## Image + container evidence

```
no backend source touched → image rebuild N/A (CLAUDE.md backend-only
                            trigger; tests-only round)
```

---

## L20 counter

| Round | Vector | Verdict |
|-------|--------|---------|
| R5 (S1) | sweep 1 — 4 single-failure scenarios + 1 doc'd test.fail | ✅ |
| R6 (S1) | consolidation re-run | ✅ |
| R10 (S1) | sweep 3 — `redirect: "error"` fix → all 5 PASS → **3/3 FULL CLEAN ⭐** | ✅ ⭐ |
| **R32 (S5)** | **round 4 deep — 3 multi-failure scenarios + Q12-L20-003 finding** | ✅ |

L20 stays at **3/3 FULL CLEAN ⭐** (round 4 is defense-in-depth deep,
not a counter bump). Q12-L20-003 is a NEW finding tracked for Sprint
22 frontend resilience pass.

---

## Delegation evidence

Self-write — the multi-failure pattern is short and the
`test.fail()` precedent is already established in the codebase (R5
L20-001 redirect-loop documentation pattern). Delegation overhead
exceeds inline write time.

---

## Next round

R33 = L19 explicit regression for S4 HIGH bugs (Q12-L22-005/006
OAuth replay, Q12-L25-004/005 body DoS, Q12-L24-007 PyJWT leak) —
pin them as backwards-compat regression tests so a future refactor
that drops the atomic-claim or middleware install fails loudly at
CI rather than silently re-opening the bug.
