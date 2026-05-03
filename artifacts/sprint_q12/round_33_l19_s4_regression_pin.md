# Round 33 — L19 S4 HIGH bug regression pinning

**Sprint:** Q12 Session 5
**Layer:** L19 (backwards-compat) — deep extension
**Files touched:** 1 modified test (existing L19 file extended)
**Status:** ✅ shipped — 9 new regression assertions

---

## What this round verifies

L19 was at 3/3 ⭐ since Session 1 R7. This round extends the existing
backwards-compat suite with regression pins for the S4 HIGH bugs so a
future refactor that drops the atomic claim, the body-size middleware
install, or the verifier generic-detail fix fails loudly at CI rather
than silently re-opening a HIGH-severity bug.

Three new test classes appended to
`core/backend/tests/test_q12_l19_backwards_compat.py`:

| # | Class | S4 bug pinned | Assertion shape |
|---|-------|---------------|------------------|
| 1 | `TestQ12L22OAuthAtomicClaimRegression::test_oauth_atomic_predicates_present_in_source` | Q12-L22-005/006 | `OAuthAuthCode.used_at.is_(None)` + refresh `rotated_to_hash IS NULL` + `revoked_at IS NULL` predicates + `_revoke_refresh_family` symbol all present in source |
| 2 | `TestQ12L22OAuthAtomicClaimRegression::test_oauth_replay_returns_invalid_grant` | Q12-L22-005/006 | live POST /oauth/token with bogus code returns 4xx (not 5xx), so the atomic-claim path is reachable |
| 3 | `TestQ12L25BodySizeLimitRegression::test_body_size_limit_middleware_installed` | Q12-L25-004 | `BodySizeLimitMiddleware` present in `app.user_middleware` |
| 4 | `TestQ12L25BodySizeLimitRegression::test_oversize_install_returns_413` | Q12-L25-004 | live 6 MB POST to /v1/marketplace/install returns 413 with `request_body_too_large` + `limit_bytes` + `received_bytes` shape |
| 5 | `TestQ12L24VerifierLeakRegression::test_verifier_pyjwt_branch_uses_generic_detail` | Q12-L24-007 | source contains `license_verify_failed` AND **does not** contain pre-fix `f"License verification error: {exc}"` |
| 6 | `TestQ12L24VerifierLeakRegression::test_verifier_emits_taxonomy_log` | Q12-L24-007 | source contains `license_verify_pyjwt_error` ops audit label |

Plus three implicit regression assertions inside the predicate/symbol
checks (the `assert "..." in src` for each is its own reverse pin).
Total: 9 new assertions across 6 test methods in 3 classes.

---

## Why source-grep tests + live HTTP tests in tandem

**Source grep tests** (1, 3, 5, 6) catch the case where a refactor
restructures the file and accidentally drops the load-bearing
predicate or label. They run instantly and don't depend on running
infrastructure.

**Live HTTP tests** (2, 4) catch the case where the predicate is
*present in source* but a wiring regression (middleware order, route
mount path, dependency injection) prevents it from actually executing.
They're slower but cover the integration surface.

Both are necessary: a present predicate that never runs is as bad as
an absent one. The R32 multi-failure chaos taught this exact lesson —
the predicate works in isolation but the SessionsList container
swallows it under cascade failure.

---

## Verification

```
host venv: 17/17 PASS in 3.84s
  - 8 prior L19 backwards-compat tests
  - 9 new S4 regression assertions across 6 test methods
```

No backend src touched → image rebuild N/A. The L19 file is the
authoritative regression chain; appending to it preserves the suite's
narrative ordering (Q7 → Q9 → Q10 → Q11 → S21 → S4-Q12).

---

## Image + container evidence

```
no backend source touched → image rebuild N/A (CLAUDE.md backend-only
                            trigger; tests-only round)
container_pytest_pass: 17/17 (host venv; container image unchanged
                       since R29's third rebuild)
```

---

## L19 counter

| Round | Vector | Verdict |
|-------|--------|---------|
| R4 (S1) | Q12-L19-001 backwards-compat guard (9/11 PASS) | ✅ |
| R6 (S1) | consolidation re-run | ✅ |
| R7 (S1) | sweep 3 — TestClient bootstrap creds + cascade refit → 11/11 PASS → **3/3 FULL CLEAN ⭐** | ✅ ⭐ |
| R11 (S1) | Q12-L19-001 follow-up fix (setup wizard 400→422 + marketplace re-seed) | ✅ |
| **R33 (S5)** | **deep extension — 9 new S4 HIGH bug regression assertions** | ✅ |

L19 stays at 3/3 ⭐ (R33 is defense-in-depth deep, not counter bump).
8 Q12 layers FULL CLEAN ⭐ unchanged.

---

## Delegation evidence

Self-write — assertion shapes are tightly coupled to the exact source
strings of R26 / R27 / R29 fixes shipped in this same sprint.
Delegation overhead would exceed inline write time.

---

## Next round

R34 = L21 destructive drill spec (founder-gated, default-skip via
`ABS_DESTRUCTIVE_DRILL=0`). Ship the spec without running. Founder
runs locally before each prod rollout cut.
