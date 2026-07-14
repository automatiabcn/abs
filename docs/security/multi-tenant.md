# Multi-Tenant Isolation — Defence in Depth

**Status:** active (3 layers; Layer 3 RLS is request-wired and extended to the tenant-data tables).
**Owner:** Security working group.
**Last updated:** 2026-06-08.

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

## Layer 3 — Postgres Row Level Security

Migration **`0015`** activated RLS on three audit tables: `customer_audit_entries`,
`webhook_events`, `vault_audit_entries`. Migration **`0019`** extended the identical
policy to the tenant-DATA tables (`0019_rls_tenant_tables`): `tenants`,
`projects`, `tenant_projects`, `provider_keys`, `tenant_settings`,
`project_members`, `chat_sessions`, `saved_workflow`, `meetings`, plus the
FK-scoped children `chat_messages` and `meeting_segments` (isolated through
their parent via an `EXISTS` sub-select). The policy clause:

```sql
USING  (tenant_slug = current_setting('abs.tenant_id', true))      -- or tenant_id
WITH CHECK (tenant_slug = current_setting('abs.tenant_id', true))
```

`ALTER TABLE ... FORCE ROW LEVEL SECURITY` applies the policy even to the table
owner. The SQLAlchemy listener (`app/db/session.py::_set_tenant_guc`) emits
`SET LOCAL abs.tenant_id = '<slug>'` before every cursor execute on Postgres,
sourced from the request-scoped `current_tenant` ContextVar.

**The wiring fix — the GUC is now actually populated.** Migration `0015` shipped
the policies + listener but the dependency meant to set the ContextVar
(`tenant_guc.py::set_request_tenant`) was never attached to a router, so in the
live request path the GUC stayed unset and the policies never engaged outside
the `postgres_only` tests. `app/middleware/tenant_context.py` (a pure-ASGI
middleware registered in `main.py`) now resolves the tenant for **every** HTTP
request — Bearer JWT `tnt` claim, else the panel `abs_session` admin cookie —
and pins it to `current_tenant` for the request's lifetime, resetting on exit.
The `/mcp` transport (a mounted sub-app authenticated by an `abs_mcp_` token,
not an OAuth JWT) bridges the same ContextVar in
`app/mcp/transport_auth.py`, so all MCP tool DB access is tenant-scoped too.

**Deliberately excluded from RLS** (a strict policy would break a real flow):
identity / pre-auth tables read by a globally-unique key before any tenant
context exists — `users` (login by email), `failed_login_attempts`,
`tenant_invites` (claim by magic-token hash), `minted_token_blacklist` (MCP
token revocation by digest — RLS here would make a *revoked* token read as
valid); and tables written from background / cascade paths that do not yet pin
the GUC — `usage_log`, `feature_usage_log`, `tenant_installed_plugins`. These
stay protected by Layers 1 + 2 and their globally-unique constraints.

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

## Risk register

| # | Risk | Status / mitigation |
|---|------|---------------------|
| 1 | Layer 1 filter forgotten in a new endpoint | PR review + ruff custom rule on raw `select(Audit*)` | 
| 2 | Cerbos fail-open emergency switch | Convert to a time-boxed feature flag with an audit emit |
| 3 | RLS active on Postgres only; SQLite tests cannot exercise it | CI matrix postgres lane (`.github/workflows/ci-postgres.yml`) runs the `postgres_only` suite |
| 4 | Operator console must use the admin pool | DSN env var `ABS_ADMIN_DATABASE_URL`; ops runbook pins the GRANT |
| 5 | Tenant-data tables without RLS | **Done (`0019`)** — 10 tenant-data tables enrolled; identity/pre-auth + background-write tables deliberately excluded (see Layer 3). New tenant-data table → add to `0019`'s `_DIRECT`/`_CHILD` + a case in `test_rls_tenant_tables.py` |
| 6 | Background worker / MCP forgets to pin the GUC | Default is None → no GUC → reads return 0 rows, writes fail loudly with 403 (chaos test). MCP transport bridges via `transport_auth.py`; remaining background writers stay on excluded tables until wired |
| 7 | HTTP route without the GUC populator | **Closed** — `TenantContextMiddleware` runs for every request (not a per-route dep), so no route can forget it |

## Linked artefacts

- `docs/operations/rls-admin-bypass.md` — production deploy steps.
- `core/backend/alembic/versions/0014_tenant_id_audit_tables.py`
- `core/backend/alembic/versions/0014b_backfill_tenant_id.py`
- `core/backend/alembic/versions/0015_rls_audit_tables.py`
- `core/backend/alembic/versions/0015b_abs_admin_role.py`
- `core/backend/alembic/versions/0019_rls_tenant_tables.py` (10 tenant-data tables)
- `core/backend/app/db/session.py::_set_tenant_guc`
- `core/backend/app/api/v1/tenant_guc.py`
- `core/backend/app/middleware/tenant_context.py` (pure-ASGI GUC populator, the keystone)
- `core/backend/app/mcp/transport_auth.py` (MCP transport → GUC bridge)
- `core/backend/app/middleware/rls_violation_handler.py`
- `core/backend/tests/integration/test_rls_audit_tables.py` (5 cases)
- `core/backend/tests/integration/test_rls_tenant_tables.py` (provider_keys + chat + meetings child)
- `core/backend/tests/integration/test_admin_bypass_rls.py` (2 cases)
- `core/backend/tests/test_tenant_context_middleware.py` (10 cases, SQLite lane)
- `core/backend/tests/chaos/test_rls_chaos_drop_guc.py` (4 cases)
- `.github/workflows/ci-postgres.yml` — runs the `postgres_only` RLS suites
