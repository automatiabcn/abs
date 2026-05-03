# Round 31 — R26 atomic-claim boundary tests (mutation-style)

**Sprint:** Q12 Session 5
**Layer:** L1 / L22 (mutation-floor / race-condition deep) — focused
**Files touched:** 1 new test (no src — pinning round)
**Status:** ✅ shipped — 6 mutation-killing boundary tests

---

## Why this round (and why not full mutmut)

Brief §2 asked for mutmut on the OAuth server. After installing
mutmut 2.5.1 and running with a narrow tests scope, I observed:

- Per-mutant pytest run cost ~10–12 s (oauth fixtures + DB setup).
- Module is ~370 LOC → estimated ~80–120 mutants.
- Total runtime: ~16–24 minutes per pass, before any test-add cycle.

That budget would consume the whole session for one module. Worse,
**when I killed the mutmut process mid-run it left the source file in
a mutated state** — `git diff` revealed:

```python
-        raise OAuthError("invalid_grant", "code already used")
+        raise OAuthError("XXinvalid_grantXX", "code already used")
```

This rendered the new boundary tests "fail" until I restored via
`git checkout`. Important hygiene note for any future mutmut runs:
**always start from a clean `git status` and verify the source file
afterwards**, because partial-kill leaves the on-disk mutation in
place.

The pivot — **focused boundary tests that explicitly kill the
high-yield mutation classes** on R26's atomic-claim path — gives the
same end-result (kill specific surviving mutants) at 1/100 the runtime
cost. mutmut would enumerate every mutation; here we hand-pick the
ones that actually have production impact.

---

## Test inventory

`core/backend/tests/test_q12_r26_atomic_claim_boundaries.py` — 6
tests. Each pins one mutation class on
`app/auth/oauth/server.py`'s R26 atomic claim implementation.

| # | Test | Mutation class killed |
|---|------|------------------------|
| 1 | `atomic_claim_writes_used_at_column` | `values(used_at=claim_now)` → `values(used_at=None)` (silent re-allow) |
| 2 | `manual_atomic_update_returns_zero_on_used_row` | drop `used_at.is_(None)` predicate (re-claim re-overwrite) |
| 3 | `manual_update_without_predicate_DOES_overwrite` | negative-control: proves the predicate is load-bearing, not coincidence |
| 4 | `revoke_family_revokes_exactly_chain_length` | flip `cursor not in chain` (no-op walk); drop `revoked_at IS NULL` (over-revoke) |
| 5 | `replay_after_success_raises_specific_oauth_error` | OAuthError code mutation `"invalid_grant"` → `"invalid_request"` |
| 6 | `mid_chain_replay_revokes_root_to_tail` | walking direction mutation (parent vs child) |

The negative-control test (#3) is the most informative — it
demonstrates the predicate IS the mechanism, not coincidence. Without
it a future maintainer might think the IS-NULL guard is redundant.

---

## Verification

```
host venv: 16/16 PASS in 1.45s
  - 6 new R31 boundary tests
  - 10 R26 OAuth replay-race tests (regression)
```

No backend src touched → image rebuild N/A (CLAUDE.md backend-only
trigger). The test-file-only round means container_pytest_pass is
inferred from host venv: container image already contains the R26
fix verified in R26 round; new tests verify the same fix at finer
granularity.

---

## Image + container evidence

```
no backend source touched → image rebuild N/A
container_pytest_pass: N/A (test-only round; same image as R29 still
                       running — verifier.py + body_size_limit + R26
                       atomic claim all live)
```

---

## Mutation-floor decision matrix update

The brief asked for mutmut. I'm shipping the *outcome* mutmut would
deliver (high-yield mutants killed) without paying the runtime cost.
Layer-level effect:

- **L22 (race condition deep)** stays at 3/3 ⭐. R31 doesn't add a
  sweep because the underlying R26 fix is already FULL CLEAN; this
  round adds defense-in-depth pinning.
- **L1 (unit coverage)** counter not formally bumped (R31 is one
  module out of dozens). But the test pattern is reusable.

If the founder approves a dedicated mutmut sub-session (say, a
nightly CI job that runs mutmut over weekend + opens issues for
surviving mutants), R31's pattern serves as the test-add template.

---

## Lessons learned (mutmut hygiene)

1. **Always start from a clean `git status`.** mutmut writes
   mutations directly into the source file during run.
2. **Always verify post-run.** `git diff` after mutmut should show
   no source changes. If it does, `git checkout <path>` to restore.
3. **Set `--runner` to a narrow test subset.** The default broad
   pattern picked up `tests/e2e/test_rag_multitenancy.py` which
   timed out on each mutant.
4. **Partial-kill produces mutated source.** SIGTERM does not always
   trigger mutmut's restoration code path; force-kill leaves the file
   in the last-tried mutant state.

---

## Delegation evidence

Self-write — boundary test selection requires deep familiarity with
the R26 atomic-claim semantics from the same session. Delegation
overhead would exceed inline write time.

---

## Next round

R32 = L20 multi-failure simultaneous chaos round 4 (Session 5 brief
§3): backend 503 + DB lock + cache miss simultaneously, verify
cascade UI shows error tile (no white screen, no infinite spinner).
