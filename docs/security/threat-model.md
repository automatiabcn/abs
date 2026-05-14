# ABS Threat Model — Cross-Tenant Data Exposure

**Status:** living document; revisit on every sprint that adds
schema, RBAC, or new tenant-scoped resources.
**Owner:** Security working group.
**Last updated:** 2026-05-14 (Sprint 2K — Postgres RLS).

## In scope

This document focuses on cross-tenant data exposure on the SaaS
control plane:

- audit logs (`customer_audit_entries`, `webhook_events`,
  `vault_audit_entries`)
- RAG documents and vector embeddings (Qdrant per-tenant collections)
- meetings, chat sessions, tenant-installed plugins
- billing artefacts (Stripe customer + license records)

Out of scope here: web-app XSS, dependency CVEs, secret leakage —
those are tracked in `docs/security/owasp_rag_checklist.md` and the
`security-nightly.yml` SCA pipeline.

## Adversary model

| Persona | Capability assumed |
|---------|--------------------|
| External attacker with a valid customer JWT | Can mint API calls but only with their own `tnt` claim. |
| Compromised employee account (operator) | Has admin cookie session + access to the operator console DSN. |
| Insider with read-only DB access (analytics, BI) | Can run psql against a replica; should *not* see cross-tenant rows. |
| Bug in our own code | Hand-written raw SQL, a fail-open Cerbos switch, or a forgotten `WHERE tenant_id` clause. |

## Asset → defence matrix

| Asset | Layer 1 (app filter) | Layer 2 (Cerbos PDP) | Layer 3 (Postgres RLS) | Notes |
|-------|----------------------|----------------------|------------------------|-------|
| `customer_audit_entries` | ✅ SQLModel queries filter on `license_jti`/tenant | ✅ `audit_log` policy | ✅ Sprint 2K — FORCE + BYPASSRLS role | KVKK/GDPR audit trail — highest blast radius |
| `webhook_events` | ✅ filter by `license_jti` | ✅ `webhook` policy | ✅ Sprint 2K | Stripe PII + plan tier |
| `vault_audit_entries` | ✅ filter by `actor` claim | ✅ `vault` policy | ✅ Sprint 2K | Vault key rotations |
| `licenses` | ✅ via owner email | ✅ `license` policy | ⏳ Sprint 2L enrolment | Customer identity |
| `meetings`, `chat_*`, `feature_usage_log`, `usage_log`, `data_export_jobs`, `tenant_invites`, `tenant_installed_plugins` | ✅ tenant_slug | ✅ resource policies | ⏳ Sprint 2L enrolment | Defence in depth gap until 2L |
| Qdrant vectors | ✅ per-tenant collection name | ✅ pre-Qdrant Cerbos gate (T-012) | n/a (Qdrant has no RLS) | Cross-tenant DENY enforced pre-RPC |

## Attack scenarios reviewed

### S1 — Forged JWT with another tenant's `tnt`

Mitigation: RS256 signatures verified against the JWKS; refresh
tokens are single-use rotation; magic-link path requires email
control. Without the matching signing key the attacker cannot reach
any of the three layers.

### S2 — Cerbos fail-open emergency switch left on

Layer 2 collapses. Layer 1 still filters at the ORM and Layer 3
(Sprint 2K) still enforces tenant match at the DB. A combined
"emergency switch on" + "ORM filter forgotten on a new endpoint"
incident is required for actual cross-leak. **Sprint 2L tracking:**
convert the switch to time-boxed flag with audit emit.

### S3 — Admin tool with raw SQL forgets `WHERE tenant_id`

Layer 1 doesn't help (raw SQL bypasses the ORM). Layer 2 is unaware
(no PDP call). Layer 3 catches it: a SELECT under `abs_app` returns
0 rows when no GUC is set (FORCE RLS). An INSERT raises SQLSTATE
42501, which the FastAPI handler converts to `403
tenant_isolation_required`
(`app.middleware.rls_violation_handler`). Verified by
`tests/chaos/test_rls_chaos_drop_guc.py`.

### S4 — Operator account compromise

Compromised operator has access to the `abs_admin` DSN — full audit
read on the 3 guarded tables. Mitigations: SSO with hardware key,
quarterly password rotation, `pg_stat_activity` audit of who used
`abs_admin`. Detection > prevention here; the role boundary is
intentional so audit logging is mechanically straightforward.

### S5 — Cascade cache cross-tenant leak (UAT-016, closed Sprint 2I)

Pre-fix: a shared in-process cache keyed on the prompt text returned
another tenant's cached completion. Fix: cache key includes
tenant_slug namespace + signed digest. Layer 3 doesn't apply
(in-process cache, not DB). Tracked in `SPRINT_2I_REPORT.md`.

### S6 — Background worker writes without GUC

Layer 3 catches it: `INSERT` without GUC fails with SQLSTATE 42501 →
job retries through Inngest DLQ → on-call alert. Verified by the
chaos suite. Workers must explicitly call `with_tenant(slug)` or
operate as the `abs_admin` role for cross-tenant infra jobs.

## Residual risk after Sprint 2K

- 9 tables still without Layer 3 (Sprint 2L scope).
- SQLite test lane cannot exercise Layer 3 — relies on the new
  postgres CI lane catching regressions before merge.
- `_unknown` rows pre-existing in the audit tables before the
  backfill ran: manual review during initial production deploy
  (founder action, runbook step 4).

## Linked artefacts

- `docs/security/multi-tenant.md` — defence chain narrative.
- `docs/operations/rls-admin-bypass.md` — production deploy steps.
- `_agent-tasks/AUDIT_3RD_EYE_2026_05_14.md` — finding #16 closed.
- `_agent-tasks/SPRINT_2I_REPORT.md` — UAT-016 cascade cache fix.
- `_agent-tasks/SPRINT_2K_REPORT.md` — closeout artefacts.
