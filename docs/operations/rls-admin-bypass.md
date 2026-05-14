# RLS Admin Bypass — Operations Runbook

**Audience:** Founder / on-call operator running production deploys.
**Owner:** Sprint 2K (Postgres RLS migration).
**Last updated:** 2026-05-14.

## Why this exists

Sprint 2K enables Postgres Row Level Security on three audit tables:

- `customer_audit_entries`
- `webhook_events`
- `vault_audit_entries`

The policies match each row's `tenant_id` against the session GUC
`abs.tenant_id`. The application sets that GUC at the start of every
request (see `app/db/session.py::_set_tenant_guc`). For operator-facing
queries that legitimately span tenants — the admin audit console, the
support engineer pulling a Stripe webhook for one customer, the nightly
GDPR purge worker — we need a Postgres role that **bypasses** RLS
instead of silently returning zero rows.

That role is `abs_admin`. Migration `0015b_abs_admin_role` creates it
with `BYPASSRLS NOLOGIN NOINHERIT`. The login + grant step is
intentionally manual so an unfinished deploy cannot become a route to
admin DB access.

## One-time production setup (founder action)

Run on the Hetzner Postgres cluster after `alembic upgrade head`
completes for the first time.

```sql
-- 1. Confirm the role exists (migration 0015b should have created it).
SELECT rolname, rolbypassrls, rolcanlogin
FROM pg_catalog.pg_roles
WHERE rolname IN ('abs_admin', 'abs_app');

-- 2. Allow the role to authenticate and set its password (use 1Password / sops).
ALTER ROLE abs_admin WITH LOGIN PASSWORD :'admin_password';

-- 3. Grant the privileges admin queries actually need (read across tenants
--    on the three RLS-guarded audit tables; nothing else).
GRANT CONNECT ON DATABASE abs_prod TO abs_admin;
GRANT USAGE ON SCHEMA public TO abs_admin;
GRANT SELECT ON
    customer_audit_entries,
    webhook_events,
    vault_audit_entries
TO abs_admin;
```

`abs_app` (the regular application role) **must not** carry
`BYPASSRLS`. Confirm with the first query above — `rolbypassrls` should
be `f` for `abs_app` and `t` for `abs_admin`.

## DSN topology

Two connection strings, two pools:

| Use case | Role | Env var |
|----------|------|---------|
| Application requests (FastAPI, Inngest workers) | `abs_app` | `ABS_DATABASE_URL` |
| Operator console audit view + GDPR purge worker | `abs_admin` | `ABS_ADMIN_DATABASE_URL` |

The application code only opens `ABS_DATABASE_URL`. The admin console
opens an explicit `abs_admin`-roled engine for the few queries that
need to read across tenants. Routing one process through two roles is
intentional: the role boundary shows up in `pg_stat_activity`, so an
auditor can prove which queries ran with bypass.

## Rotating the admin password

```sql
ALTER ROLE abs_admin WITH PASSWORD :'new_admin_password';
-- Restart the operator console pod so it picks up the new DSN from sops.
```

Rotate on the same cadence as the SOPS vault key — currently quarterly.

## Smoke test after deploy

```bash
# As abs_app — should return 0 rows when no GUC is set (FORCE RLS).
psql "$ABS_DATABASE_URL" -c "SELECT count(*) FROM customer_audit_entries"
# Expected: 0

# As abs_app with the right GUC — should return that tenant's rows.
psql "$ABS_DATABASE_URL" -c "SET abs.tenant_id = 'acme'; SELECT count(*) FROM customer_audit_entries"
# Expected: that tenant's count

# As abs_admin — BYPASSRLS, sees everything regardless of GUC.
psql "$ABS_ADMIN_DATABASE_URL" -c "SELECT count(*) FROM customer_audit_entries"
# Expected: total count across all tenants
```

A non-zero `abs_app` count without a GUC is a regression — file a P0
and re-check that the migration ran on this cluster.

## Why the policy uses `FORCE`

`ALTER TABLE ... FORCE ROW LEVEL SECURITY` makes the policy apply even
to the table owner. Without `FORCE`, a connection that happens to log
in as the schema owner (anyone with `superuser` privileges, including
some legacy DB tools) silently bypasses the policy. We force; the
documented escape hatch is the `abs_admin` role, nothing implicit.

## Downgrade behaviour

`alembic downgrade` past `0015_rls_audit_tables` drops the policies but
leaves `abs_admin` in place — the role is harmless without the
matching policies, and dropping it would invalidate `pg_dump` exports
that referenced it. Run the `0015b` downgrade explicitly if you need a
clean revert; on dev/staging clusters the role drops cleanly, on prod
the drop fails if the role still owns objects (intentional safety
catch).

## Linked policies

- `core/backend/alembic/versions/0015_rls_audit_tables.py`
- `core/backend/alembic/versions/0015b_abs_admin_role.py`
- `core/backend/app/db/session.py::_set_tenant_guc`
- `core/backend/app/api/v1/tenant_guc.py::set_request_tenant`
- `docs/security/multi-tenant.md` — defence-in-depth layer view.
