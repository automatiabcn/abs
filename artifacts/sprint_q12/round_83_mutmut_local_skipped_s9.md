# Round 83b — Mutmut local actual run (Session 9)

**Sprint:** Q12 Session 9
**Layer:** mutation testing — 4th session SKIP
**Status:** SKIPPED — founder gate not opened in S9

---

## Why skipped

S9 brief carries the same gate language as S6–S8: founder explicitly
told the worker to keep `ABS_MUTATION_RUN=1` closed in this session.
The brief lists Mutmut actual under **"LOW (founder yine SKIP dedi —
bu session'da da SKIP commit)"**.

Default behaviour stays SKIP + artifact note. Cumulative skip count
across S6 R39 / S7 R54 / S8 / S9 → **4 sessions**.

## What is already shipped (no regression in scope)

- `.github/workflows/mutation-weekend.yml` — full mutmut matrix
  cron Saturday 02:00 UTC, plus the **R80-locked** `fuzz-30k`
  job 5-pytest contract (this session)
- Module list in the matrix is the source of truth; local run is
  only a "cut-the-cron-runtime" optimisation, never a substitute
  for the weekend matrix run

## How to invoke locally (when founder is ready)

```bash
ABS_MUTATION_RUN=1 cd core/backend && \
  ./.venv/bin/mutmut run \
    --paths-to-mutate=app/auth/oauth/server.py \
    --tests-dir=tests/
```

S5 R31 measured: 16-24 minutes for a single critical module on a
laptop. The full weekend matrix is unchanged.

## Counters

- Backend pytest: unchanged from R82 close (**1753 / 14 skipped**).
- Mutmut local module reports: 0 produced this session.
- Atomic commits: 1 covering both this artifact + the L21
  companion (R83a).
