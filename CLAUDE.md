# ABS Server — Repository Guide

ABS (Automatia BCN Self-host) is a self-hostable AI orchestration product:
a unified gateway over multiple LLM providers with RAG, a knowledge graph,
meeting transcription, workflows, an admin panel, and an MCP tool surface.

The product ships globally — **default language is English**, with TR/ES as
alternate locales (i18n). Never hard-code a single locale in user-facing copy.

## Stack

- **Backend:** FastAPI + SQLModel (SQLite by default; Postgres supported via
  Alembic migrations), provider cascade, Qdrant (vectors), Neo4j (graph),
  Cerbos (RBAC), sops/age vault for secrets.
- **Landing/Panel:** Next.js (App Router) + Tailwind, admin panel under
  `/admin/*`.
- **Infra:** Docker Compose + Caddy reverse proxy.

## Layout

```
core/backend/        FastAPI app (app/), tests (tests/), alembic/ migrations
core/landing/        Next.js panel + marketing site
infra/               docker-compose + Caddyfile + deploy scripts
docs/                product documentation
```

## Running tests

```bash
# Backend
cd core/backend && python -m pytest -q

# Landing
cd core/landing && npm test            # vitest
npx tsc --noEmit                        # type-check
```

## Conventions

- Migrations: add an Alembic revision under `core/backend/alembic/versions/`
  for any new table (Postgres deployments run `alembic upgrade head` on boot;
  SQLite uses `create_all`). Keep revision ids ≤ 32 chars.
- New features should be additive and opt-in; never regress existing flows.
- Multi-tenant: data is tenant-scoped (`tenant_id`); per-project scoping uses
  the `X-Project-Id` header. Provider keys resolve project → user → org →
  global.
- Author attribution is collective ("Automatia BCN engineering"); do not put
  individual names, personal file paths, or internal infrastructure details in
  committed files.
