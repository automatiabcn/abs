# Round 26 — L22 sweep 3 OAuth atomic single-use enforcement

**Sprint:** Q12 Session 4
**Layer:** L22 (race condition deep) — sweep 3
**Files touched:** 1 src + 1 new test
**Status:** ✅ shipped — **L22 → 3/3 FULL CLEAN ⭐** (7 Q12 layers FULL CLEAN total)

---

## Real bugs surfaced

### Q12-L22-005 (HIGH security — token replay) — `exchange_code_for_tokens` read-then-write race

OAuth 2.1 §4.1.3 requires the authorization code to be **single-use**. The
production code did a non-atomic read-then-write on
`OAuthAuthCode.used_at`:

```py
record = first_or_none(db, select(OAuthAuthCode).where(...))
if record.used_at is not None:
    raise OAuthError("invalid_grant", "code already used")
...
record.used_at = _now()
db.add(record); db.commit()
```

Two concurrent /oauth/token requests with the same `code` could both
read `used_at = None` before either committed. Both passed the guard,
both committed, **both minted access+refresh token pairs** — full
token replay. Captured Session ≠ secure session.

**Pre-fix proof (host venv):**
```
tests/test_q12_l22_oauth_replay_race.py::test_q12_l22_005_two_session_replay_blocked
FAILED — DID NOT RAISE OAuthError (both sessions returned tokens)
```

### Q12-L22-006 (HIGH security — refresh chain split) — `refresh_access_token` read-then-write race

Same pattern on `OAuthRefreshToken.rotated_to_hash`. Concurrent refresh
requests could rotate the same parent twice → 2 valid child chains.
OAuth 2.1 §6.1 additionally mandates that on detected refresh-replay
the AS revoke the **entire token family** to contain leaked tokens.
Pre-fix: replay was hard-stopped on the second sequential call, but
*concurrent* replay went undetected and there was no family revocation.

---

## Fixes shipped

`core/backend/app/auth/oauth/server.py`:

1. **Atomic auth-code claim** (Q12-L22-005)
   ```py
   claim_stmt = (
       sa_update(OAuthAuthCode)
       .where(OAuthAuthCode.code == code)
       .where(OAuthAuthCode.used_at.is_(None))
       .values(used_at=claim_now)
   )
   claim_result = db.execute(claim_stmt); db.commit()
   if (claim_result.rowcount or 0) != 1:
       logger.warning("oauth_code_replay_blocked client_id=%s ...", client_id)
       raise OAuthError("invalid_grant", "code already used")
   ```
   The `WHERE used_at IS NULL` predicate makes the claim atomic — the
   DB engine guarantees exactly one transaction observes
   `rowcount == 1`. The pre-existing read-time guard remains as the
   fast-path replay detector and now emits
   `oauth_code_replay_attempt` for ops audit.

2. **Atomic refresh rotation claim** (Q12-L22-006)
   ```py
   rotate_stmt = (
       sa_update(OAuthRefreshToken)
       .where(OAuthRefreshToken.token_hash == presented_hash)
       .where(OAuthRefreshToken.rotated_to_hash.is_(None))
       .where(OAuthRefreshToken.revoked_at.is_(None))
       .values(rotated_to_hash=new_hash)
   )
   ```
   Same shape, three predicates: token match + not-yet-rotated +
   not-revoked. Loser of the race triggers family revocation.

3. **Family revocation helper** — OAuth 2.1 §6.1 compliance
   ```py
   def _revoke_refresh_family(db, start_hash):
       chain = []; cursor = start_hash
       while cursor and cursor not in chain:  # cycle-safe
           chain.append(cursor)
           nxt = first_or_none(db, select(...).where(token_hash == cursor))
           cursor = nxt.rotated_to_hash if nxt else None
       db.execute(sa_update(...).where(token_hash.in_(chain))
                  .where(revoked_at.is_(None))
                  .values(revoked_at=now))
   ```
   Cycle-safe (`cursor not in chain`) so a corrupt chain does not loop
   forever. Bulk UPDATE w/ `revoked_at IS NULL` predicate makes the
   revocation idempotent under concurrent attempts.

4. **Audit trail (Q12-L23 continuation)** — three new warning labels:
   - `oauth_code_replay_attempt` — fast-path post-use replay
   - `oauth_code_replay_blocked` — atomic claim lost the race
   - `oauth_refresh_replay_blocked` — refresh chain replayed
   - `oauth_refresh_race_blocked` — refresh atomic claim lost the race

---

## Test inventory

`core/backend/tests/test_q12_l22_oauth_replay_race.py` — 10 new tests
(all 10 PASS post-fix; 1 of 10 proven to FAIL pre-fix via `git stash`).

| # | Test | Vector |
|---|------|--------|
| 1 | `005_two_session_replay_blocked` | Two stale ORM Session copies → 1 succeeds, 1 invalid_grant |
| 2 | `005_threaded_race_only_one_succeeds` | ThreadPoolExecutor + barrier → 1 success, 1 err |
| 3 | `005_post_use_replay_emits_warning` | Audit emit for replay-attempt taxonomy |
| 4 | `005_normal_flow_still_works` | Regression guard |
| 5 | `006_two_session_refresh_replay_blocked` | Refresh stale-Session race |
| 6 | `006_threaded_refresh_race_only_one_succeeds` | Refresh threaded race |
| 7 | `006_replay_revokes_family` | OAuth 2.1 §6.1 family revocation chain walk |
| 8 | `006_replay_emits_warning` | Audit emit for replay-blocked taxonomy |
| 9 | `006_normal_rotation_unaffected` | 3-step rotation regression guard |
| 10 | `006_revoke_family_cycle_safe` | Cycle-detection in chain walk |

---

## Pre-fix vs post-fix comparison (host venv)

```
git stash push -- core/backend/app/auth/oauth/server.py
cd core/backend && ./.venv/bin/python -m pytest tests/test_q12_l22_oauth_replay_race.py -x
→ FAILED — DID NOT RAISE OAuthError (1 failed before fix-stop)
git stash pop
→ 10 passed in 1.25s
```

OAuth+auth regression suite (33 sibling tests) post-fix:
```
tests/test_t003_oauth_server.py        9/9 PASS
tests/test_t003_oauth_routes.py        6/6 PASS
tests/test_q12_l22_oauth_replay_race   10/10 PASS
tests/test_t008_auth_events.py         9/9 PASS
─── 34 passed in 10.89s
```

---

## Image + container evidence

```
image_rebuilt_at: 2026-05-03T13:02:36Z (Q12 Session 4 first rebuild)
container_file_present: /app/tests/test_q12_l22_oauth_replay_race.py ✓
container_emit_event_count: server.py: 10 (sa_update + 4 warning labels +
                            _revoke_refresh_family + 2× claim + 1× helper)
container_pytest_pass: 10/10 (host venv; container is prod image w/o pytest,
                       Session 3 verification pattern)
```

Live curl smoke (backend port 8000, default infra-backend-1):
```
POST /oauth/token (no body)        → 422 (FastAPI form validation)
POST /oauth/token (bogus client)   → 400 invalid_client
                                     {"error":"invalid_client",
                                      "error_description":"unknown client bogus"}
```

Endpoint serving the new image; pre-claim guards still respond
correctly without leaking internals (Q12-L24 regression-checked).

---

## L22 counter

| Sweep | Round | Vector | Verdict |
|-------|-------|--------|---------|
| 1 | R15 (S2) | Setup wizard 7-endpoint TOCTOU + fcntl.LOCK_EX | ✅ |
| 2 | R23 (S3) | Vault rotate concurrent-race + RotationBusyError | ✅ |
| 3 | **R26 (S4)** | **OAuth code+refresh atomic claim + §6.1 family revoke** | ✅ |

**Result: L22 → 3/3 FULL CLEAN ⭐** (7 Q12 layers FULL CLEAN total:
L17, L18, L19, L20, L23, L24, **L22**).

---

## Delegation evidence

- `mcp__abs__ask_gptoss` — atomic UPDATE-with-rowcount pattern + family
  revocation traversal sketch (≈40 LOC; adapted to UTC-naive timestamps
  + full refresh row + emit_event taxonomy).

Self-write portion: production-grade adaptation (column expression
typing, log labels, cycle-safe walk, fast-path warning preservation,
test fixtures matching codebase conventions).

---

## Next round

R27 — L22 sweep 4 candidate: cascade routing concurrency under 100
parallel chat reqs (provider state-machine race) **OR** L25 sweep 3
RAG ingest batch DoS + plugin install 50MB cap. Picking by audit-floor
priority.
