# Round 38 — L21 destructive drill ACTUAL run

**Sprint:** Q12 Session 6
**Layer:** L21 (fresh-deploy drill) — sweep 4 ACTUAL run
**Status:** ⏸ SKIPPED — pending founder approval

---

## Why skipped

Brief explicitly:

> **FOUNDER ONAY GEREKLİ** — bu komutu çalıştırmadan önce
> founder'a sor. Onay yoksa SKIP, `L21_destructive_run: SKIPPED
> — pending founder approval` not düş.

Auto-mode safety: "Anything that deletes data or modifies shared
or production systems still needs explicit user confirmation."
The S5 R34 destructive drill is a 3-iteration `rm -rf data/` +
postgres+redis docker-compose down + alembic upgrade head loop.
Even though the spec uses an isolated namespace
(`q12-l21-drill` + port 28000), it still mutates real Docker
volumes on the host.

No founder approval received in Session 6; the actual run is
deferred to a future session where the founder explicitly
authorises it.

## What is shipped (S5)

The drill *spec* + *script* are already committed (S5 R34,
commit `0f787cd`):

- `scripts/chaos/destructive_drill.sh` — 7-step drill script
- `tests/test_q12_l21_destructive_drill_spec.py` — 7/7 tests PASS
  (script syntax + safety guards + isolation namespace asserts)

A founder running `ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash
scripts/chaos/destructive_drill.sh` locally is the only remaining
step. The Q12-L21 layer matrix counter remains at **3/3 ⭐ spec**
(was 3/3 ⭐ spec at S5 close) — graduating to 4/3 deep waits for
the actual run.

## How to actually run (when founder approves)

```bash
# 1. Confirm clean working tree
git status

# 2. Run the drill (3 iterations ≈ 3-5 minutes, isolated namespace)
ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash scripts/chaos/destructive_drill.sh

# 3. Capture output (drift, residual containers, alembic upgrade timings)
# 4. Round 38 artifact: paste the run log + assert SUCCESS_COUNT == 3
```

## Counters

- Backend pytest: unchanged 1633 PASS / 14 skipped.
- Playwright: unchanged.
- Atomic commits in round: 1 (this artifact).
- L21 layer counter: **3/3 ⭐ spec** (no graduation without actual run).
