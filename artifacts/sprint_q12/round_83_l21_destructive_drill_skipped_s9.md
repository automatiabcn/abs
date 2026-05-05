# Round 83a — L21 destructive drill ACTUAL run (Session 9)

**Sprint:** Q12 Session 9
**Layer:** L21 (fresh-deploy drill) — sweep 5 ACTUAL run (5th session SKIP)
**Status:** SKIPPED — founder gate not opened in S9

---

## Why skipped

S9 brief carries the same gate language as S5–S8: the founder
explicitly told the worker to keep `ABS_DESTRUCTIVE_DRILL=1` closed
in this session. The brief lists L21 actual under **"LOW (founder yine
SKIP dedi — bu session'da da SKIP commit)"**.

Default behaviour stays SKIP + artifact note. Cumulative skip count
across S5 R12 / S6 R38 / S7 R53 / S8 / S9 → **5 sessions**.

## What is already shipped (no regression in scope)

- `scripts/chaos/destructive_drill.sh` — drill executor
  (S5 R34 commit `0f787cd`)
- `core/backend/tests/test_q12_l21_destructive_drill_spec.py` —
  7/7 spec tests
- Companion `scripts/dr/backup_restore_drill.sh` shipped in **R77 (this session)**
  for data-durability variant; both sit behind separate env gates
  (`ABS_DESTRUCTIVE_DRILL=1` vs `ABS_DR_DRILL=1`).

## How to invoke (when founder is ready)

```bash
ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 \
  bash scripts/chaos/destructive_drill.sh
```

Isolated `q12-l21-drill` compose namespace, port 28000. Refuses
infra-* / abs-cj namespaces (safety guard). Step 7 exercises the
live R27 BodySizeLimit (60 MB → 413).

## L21 layer counter

Stays at **3/3 ⭐ spec** (no graduation to 4/3 deep without an
actual run log).

## Counters

- Backend pytest: unchanged from R82 close (**1753 / 14 skipped**).
- Atomic commits: 1 covering both this artifact + the Mutmut
  companion (R83b).
