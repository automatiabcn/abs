# Mutation Weekend Policy (Q12 R41)

## Why a separate cron job

`mutmut` mutates the source tree at runtime, then runs the test
suite once per mutation. Empirically (Q12 S5 R31, on
`app/auth/oauth/server.py`) a single critical module takes
**16–24 minutes** to mutate. Running this on every PR would push
CI from ~6 minutes to ~30+ minutes for any auth/cascade change —
unacceptable.

The compromise: run mutmut only on the **weekend off-hours
window** (Sat 02:00 UTC, see
[`.github/workflows/mutation-weekend.yml`](../../.github/workflows/mutation-weekend.yml)),
against the three highest-yield modules:

- `app/cascade` (router correctness, fallback chain integrity)
- `app/auth/oauth` (token issuance / refresh / revocation)
- `app/api/auth` (login + session cookie surface)

A surviving mutant **does NOT fail the build.** It is uploaded as
an artifact (`mutmut-<module>`) and surfaced in
`$GITHUB_STEP_SUMMARY`. The on-call engineer reviews the report
on Monday and decides whether to:

1. add a focused boundary test that kills the surviving mutant
   (S5 R31 "mutation-floor pinning" pattern), OR
2. mark the mutation as semantically equivalent / harmless and
   move on.

## Triage flow

```
weekend job → artifact   →   Monday review (on-call)
                              ├── add a regression test
                              │   (referencing the surviving
                              │   mutation in the test docstring)
                              └── document why the mutation is
                                  equivalent in the audit log
```

## Pivoted vs. blocking

The S5 R31 pivot — write a focused test instead of running full
mutmut — is still the recommended pattern when the survivor is
known up-front. The weekend job catches the *unknown* survivors
that no human would think to write a boundary test for.

## Manual run

```
gh workflow run mutation-weekend.yml
```

Pulls the same matrix. Useful before a release cut or after a
security audit finding.
