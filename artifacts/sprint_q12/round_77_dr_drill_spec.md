# Round 77 — DR backup-restore drill spec (founder-gated, isolated namespace)

**Date:** 2026-05-04 (Q12 Session 9)
**Branch:** `feat/sprint-q12-deep-quality`
**Layer:** Q12-L28 (NEW — data durability drill)
**Commits:** 1 atomic (this round)

## Goal

Ship a founder-gated DR backup→restore drill that runs against a **disposable
docker-compose namespace**, not staging or live. Sister script to
`scripts/chaos/destructive_drill.sh` (Q12-L21) but scoped to *data durability*
rather than fresh-deploy.

The existing `scripts/dr/dr_drill.sh` (T-062) is staging-only and runs against
real S3-backed buckets. R77 adds a local sandbox variant so a contributor can
exercise the whole backup→restore path without any production access.

## Files shipped

- `scripts/dr/backup_restore_drill.sh` — DRY RUN by default, `ABS_DR_DRILL=1`
  unlocks (founder-gated). Plus a hard refusal for any namespace in
  `{infra, abs-cj, abs, q12-l21-drill}` even with the gate open.
- `core/backend/tests/test_q12_l28_dr_drill_spec.py` — 10 regression pytest
  locking the gate semantics.

## Safety contract

| Property | Behaviour | Test |
|----------|-----------|------|
| Default = DRY RUN | Exit 0, prints banner, runs no commands | `test_dry_run_default_exits_zero_with_gate_banner`, `test_unset_env_treated_as_dry_run` |
| Live namespace refusal | `ABS_DR_DRILL_PROJECT in {infra, abs-cj, abs, q12-l21-drill}` → exit 3 | `test_refuses_live_or_sister_namespace[*]` (4 cases) |
| Refusal **predates** gate | Even without `ABS_DR_DRILL=1`, an unsafe namespace errors first | `test_refusal_predates_gate_check` |
| Banner advertises defaults | Port `28100`, `3` synthetic tenants, "Postgres + Qdrant + Helm release are never contacted" must appear in DRY RUN output | `test_documents_isolated_port_and_default_tenant_count` |
| Gate-open path keeps body unshipped | `ABS_DR_DRILL=1` in a sandbox namespace prints a notice that the real-run executor is intentionally unimplemented in R77 | `test_sandbox_namespace_with_gate_open_keeps_actual_run_unshipped` |

The "refusal predates gate" test is the load-bearing one: it ensures a typo in
`ABS_DR_DRILL_PROJECT=infra` cannot ride a future gate flip into production.

## Why the actual-run body is left unimplemented

R77 ships only the **spec + safety contract + dry-run banner**. The five steps
(docker compose up → tenant seed → pg_dump + qdrant snapshot → destructive
truncate → pg_restore + smoke) are documented in the dry-run banner but not
executed. Reasons:

1. The Q12 Session 9 brief says the actual run is founder-gated and the
   founder has not approved it yet — same posture as L21 destructive drill.
2. The actual executor needs a sandbox `docker-compose` overlay that doesn't
   yet exist, and shipping the executor without that overlay would be a
   false-positive "drill ready" signal.
3. Keeping the body absent guarantees the regression test
   `test_sandbox_namespace_with_gate_open_keeps_actual_run_unshipped` can
   fail loudly the moment a future commit silently lands the body without
   founder sign-off.

## Test results

```
tests/test_q12_l28_dr_drill_spec.py::test_script_exists_and_is_executable PASSED
tests/test_q12_l28_dr_drill_spec.py::test_dry_run_default_exits_zero_with_gate_banner PASSED
tests/test_q12_l28_dr_drill_spec.py::test_unset_env_treated_as_dry_run PASSED
tests/test_q12_l28_dr_drill_spec.py::test_refuses_live_or_sister_namespace[infra] PASSED
tests/test_q12_l28_dr_drill_spec.py::test_refuses_live_or_sister_namespace[abs-cj] PASSED
tests/test_q12_l28_dr_drill_spec.py::test_refuses_live_or_sister_namespace[abs] PASSED
tests/test_q12_l28_dr_drill_spec.py::test_refuses_live_or_sister_namespace[q12-l21-drill] PASSED
tests/test_q12_l28_dr_drill_spec.py::test_sandbox_namespace_with_gate_open_keeps_actual_run_unshipped PASSED
tests/test_q12_l28_dr_drill_spec.py::test_documents_isolated_port_and_default_tenant_count PASSED
tests/test_q12_l28_dr_drill_spec.py::test_refusal_predates_gate_check PASSED
10 passed in 0.56s
```

Backend pytest delta: 1721 → **1731** (+10).

## Image rebuild gate

This round only adds a script + a test that shells out to that script;
backend code is untouched. Container exec gate not triggered.

## Followups (not this round)

- Author the `docker-compose.dr-drill.yml` overlay (isolated postgres + qdrant
  on port 28100 + sidecar) and the `core.backend.scripts.seed_drill_tenants`
  CLI used by step 2.
- Once the overlay exists, fill in the actual-run body — at which point
  `test_sandbox_namespace_with_gate_open_keeps_actual_run_unshipped` will
  start failing on purpose and the worker / founder will replace the
  assertion with a real "ran-and-passed" check.
- Wire a workflow_dispatch that runs the dry-run on every PR touching
  `scripts/dr/**` so the safety contract regressions are caught before merge.
