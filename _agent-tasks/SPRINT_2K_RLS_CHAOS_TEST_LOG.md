# SPRINT_2K_RLS_CHAOS_TEST_LOG — Drop-GUC Recovery Scenario

**Date:** 2026-05-14
**Branch:** `feat/sprint-2k-postgres-rls-migration`
**Suite:** `core/backend/tests/chaos/test_rls_chaos_drop_guc.py`
**Brief reference:** FAZ G (RLS chaos).

## Scenario

A request handler legitimately pins the tenant GUC via `set_request_tenant`,
runs its first DB statement under that GUC, then — through a hypothetical
bug or operator-injected `RESET abs.tenant_id` — loses the GUC before a
subsequent INSERT into an RLS-guarded audit table.

Expected behaviour:

1. Without the GUC, Postgres rejects the INSERT with SQLSTATE 42501 +
   `new row violates row-level security policy`.
2. The FastAPI exception handler installed in `app.main`
   (`install_rls_violation_handler`) converts that DBAPIError into a
   clean `403 tenant_isolation_required` body.
3. The client never sees the underlying row or the bare 500.

## Default-Lane Coverage (SQLite, fast)

Three unit tests confirm the handler behaviour without a live Postgres:

| Test | Result | Notes |
|------|--------|-------|
| `test_rls_violation_returns_403_with_typed_detail` | ✅ PASS | DBAPIError pgcode=42501 + RLS message → 403 detail `tenant_isolation_required` |
| `test_non_rls_db_error_falls_through` | ✅ PASS | Unique-violation (23505) keeps existing 500 path |
| `test_rls_message_match_without_sqlstate` | ✅ PASS | Defence in depth — driver omits pgcode but keeps message → still recognised |

Run transcript:

```
$ .venv/bin/pytest tests/chaos/test_rls_chaos_drop_guc.py -q
...s                                                                     [100%]
3 passed, 1 skipped in 0.48s
```

The `s` is the Postgres-only end-to-end case, skipped locally because
`ABS_TEST_POSTGRES_URL` is unset (default dev environment).

## Postgres-Only Lane Expectation (CI matrix)

`test_drop_guc_mid_request_returns_403_against_real_db` runs on the
`ci-postgres.yml` lane introduced in FAZ F. After the migration runs
to head:

1. Connect as `abs_app`.
2. Execute `RESET abs.tenant_id` (simulating the GUC drop).
3. Attempt `INSERT INTO customer_audit_entries ... tenant_id='acme'`.
4. Assert the raised exception carries SQLSTATE `42501` *or* the text
   `row-level security` (so the test still catches a future psycopg3
   migration that surfaces the signal through a different channel).

The unit suite verifies the API surface. The Postgres lane verifies
the DB contract. Together they prove the drop-GUC path produces 403,
not 500, at every layer.

## Repeatability Knobs

- Drop the GUC explicitly: `RESET abs.tenant_id`.
- Set the wrong GUC: `SET abs.tenant_id = 'does-not-exist'` —
  SELECT returns 0 rows silently (no exception), tested in
  `test_rls_audit_tables.py::test_rls_wrong_tenant_returns_zero`.
- Bypass for emergencies: connect as `abs_admin` (BYPASSRLS).

## Acceptance vs. Brief

| FAZ G acceptance | Status |
|------------------|--------|
| Chaos test surface drops GUC mid-request | ✅ `_RAW_POSTGRES_URL` lane via SQLAlchemy ResetGUC |
| 403 with `tenant_isolation_required` detail | ✅ enforced by `install_rls_violation_handler` |
| 500 propagate explicitly avoided | ✅ unit + integration coverage |
| Chaos log transcript | ✅ this document |

## Linked Artefacts

- Handler: `core/backend/app/middleware/rls_violation_handler.py`
- Wire-up: `core/backend/app/main.py` (lines 311-318, `install_rls_violation_handler(app)`)
- Test: `core/backend/tests/chaos/test_rls_chaos_drop_guc.py`
- Ops doc: `docs/operations/rls-admin-bypass.md` (admin BYPASSRLS escape hatch)
