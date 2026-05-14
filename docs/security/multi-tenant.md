# Multi-Tenant Isolation — Defence in Depth

**Status:** active (3 layers, Sprint 2K onwards).
**Owner:** Security working group.
**Last updated:** 2026-05-14.

ABS isolates tenants with three independent layers. A cross-tenant
leak requires *all three* to fail simultaneously.

## Layer 1 — Application-level tenant filter

Every SQLModel query that touches a tenant-scoped table joins on
`tenant_slug` or `tenant_id`. Code-review gate: a new endpoint that
reads from those tables must accept an authenticated principal, read
the tenant from its `tnt` claim, and include `WHERE tenant_id = :tnt`
in the resulting SQL.

| Strengths | Weaknesses |
|-----------|------------|
| Cheap, works on every dialect | Single-line bug bypasses it. Admin tools that hand-write raw SQL routinely miss the predicate. |
| Filter shape is reviewable in PRs | Cache layers (Redis, in-process) that bypass the ORM bypass the filter too. |

## Layer 2 — Cerbos PDP

Before any tenant-scoped record reaches the response, the
`projects` / `rag_resource` / `audit_log` PDP policies in `policies/`
authorise the principal-to-resource pair. The decision is logged and
cached briefly per request.

| Strengths | Weaknesses |
|-----------|------------|
| Out-of-band of the ORM — catches raw SQL too | Fail-open mode in incidents (`ABS_CERBOS_FAIL_OPEN=true` emergency switch) skips the PDP entirely. |
| Auditable, replayable | A policy gap or `*` wildcard in a new policy can re-open cross-tenant reads. |

## Layer 3 — Postgres Row Level Security (Sprint 2K)

Activated on three audit tables: `customer_audit_entries`,
`webhook_events`, `vault_audit_entries`. The policy clause:

```sql
USING  (tenant_id = current_setting('abs.tenant_id', true))
WITH CHECK (tenant_id = current_setting('abs.tenant_id', true))
```

`ALTER TABLE ... FORCE ROW LEVEL SECURITY` applies the policy even to
the table owner. The application's SQLAlchemy listener
(`app/db/session.py::_set_tenant_guc`) emits
`SET LOCAL abs.tenant_id = '<slug>'` before every cursor execute on
Postgres, sourced from the request-scoped `current_tenant` ContextVar
that `app/api/v1/tenant_guc.py::set_request_tenant` pins from the JWT
`tnt` claim. Background workers wrap their handlers with
`with_tenant(job_payload["tenant_id"])`.

| Strengths | Weaknesses |
|-----------|------------|
| Enforced inside the DB engine — even raw psql breaks | Postgres-only; SQLite test lane relies on layers 1 + 2 |
| FORCE + BYPASSRLS role split makes the escape hatch auditable | Admin queries need a separate role (`abs_admin`) |

## Escape hatch — `abs_admin`

The dedicated role created by migration `0015b_abs_admin_role` carries
`BYPASSRLS NOLOGIN NOINHERIT`. Production grants `LOGIN` + `SELECT` on
the three guarded tables manually after deploy
(`docs/operations/rls-admin-bypass.md`). The application pool stays
on `abs_app` (no bypass) so a code-path bug can't pick the wrong
connection.

## Defence chain at a glance

```
request ──► JWT decode (tnt claim)
        ──► set_request_tenant (Layer 1 filter input)
        ──► Cerbos PDP (Layer 2 authz)
        ──► SQLAlchemy listener SET LOCAL (Layer 3 GUC)
        ──► Postgres policy (Layer 3 enforce)
        ──► response

Operator (admin console) ──► abs_admin role (BYPASSRLS) ──► full audit view
```

## Risk register (post-Sprint 2K)

| # | Risk | Status / mitigation |
|---|------|---------------------|
| 1 | Layer 1 filter forgotten in a new endpoint | PR review + ruff custom rule on raw `select(Audit*)` | 
| 2 | Cerbos fail-open emergency switch | Sprint 2L: convert to time-boxed feature flag with audit emit |
| 3 | RLS active on Postgres only; SQLite tests cannot exercise it | CI matrix postgres lane (`.github/workflows/ci-postgres.yml`) runs the `postgres_only` suite |
| 4 | Operator console must use the admin pool | DSN env var `ABS_ADMIN_DATABASE_URL`; ops runbook pins the GRANT |
| 5 | Future audit tables added without RLS | Sprint 2L enrols 9 more tables (licenses, data_export_jobs, meetings, chat_sessions, chat_messages, tenant_invites, tenant_installed_plugins, feature_usage_log, usage_log) |
| 6 | Background worker forgets `with_tenant` | Default is None → no GUC set → reads return 0 rows, writes fail loudly with 403 (chaos test covers this) |

## Linked artefacts

- `docs/operations/rls-admin-bypass.md` — production deploy steps.
- `core/backend/alembic/versions/0014_tenant_id_audit_tables.py`
- `core/backend/alembic/versions/0014b_backfill_tenant_id.py`
- `core/backend/alembic/versions/0015_rls_audit_tables.py`
- `core/backend/alembic/versions/0015b_abs_admin_role.py`
- `core/backend/app/db/session.py::_set_tenant_guc`
- `core/backend/app/api/v1/tenant_guc.py`
- `core/backend/app/middleware/rls_violation_handler.py`
- `core/backend/tests/integration/test_rls_audit_tables.py` (5 cases)
- `core/backend/tests/integration/test_admin_bypass_rls.py` (2 cases)
- `core/backend/tests/chaos/test_rls_chaos_drop_guc.py` (4 cases)
- `_agent-tasks/SPRINT_2K_RLS_CHAOS_TEST_LOG.md`
