# 30-Minute Quickstart

> Zero to first RAG query in under half an hour. Tested on macOS, Ubuntu 22.04, and Debian 12.

## What you'll have at the end

- ABS backend running locally on `http://localhost:8000`.
- An organisation (a "tenant" in the API) + project provisioned via OAuth.
- One document indexed in Qdrant.
- A successful `/v1/rag/query` returning grounded results.

## Prerequisites (5 minutes)

| Tool | Version | Notes |
|---|---|---|
| Docker | 24.0+ | with Compose v2 plugin |
| Git | any | for cloning |
| `curl` | any | API smoke tests |
| Anthropic API key (or OpenAI / Groq) | — | for the LLM provider cascade |

## Step 1 — Clone & configure (3 minutes)

```bash
git clone https://github.com/automatiabcn/abs.git
cd abs
cp infra/docker-compose.demo.yml infra/docker-compose.local.yml
cp core/backend/.env.example core/backend/.env
```

Edit `core/backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
ABS_AUDIENCE_ENFORCE=false   # leave off for local
ABS_LICENSE_KEY=demo-30min   # the ABS_ prefix is the canonical name;
                             # the legacy LICENSE_KEY is auto-promoted
                             # with a deprecation warning for one
                             # release.
```

## Step 2 — Boot the stack (10 minutes)

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d
docker compose -f infra/docker-compose.qdrant.yml up -d
```

Verify:

```bash
curl -fsS http://localhost:8000/healthz       # 200 OK
curl -fsS http://localhost:6333/collections   # qdrant up
```

## Step 3 — Apply migrations (2 minutes)

```bash
docker compose exec backend alembic -c alembic.ini upgrade head
```

You should see `0000_init_baseline → … → 0003_tenant_projects`.

## Step 4 — Provision your organisation + project (5 minutes)

```bash
# 1. Register an OAuth client.
curl -fsS -X POST http://localhost:8000/oauth/clients \
  -H "Content-Type: application/json" \
  -d '{"client_id":"demo","redirect_uris":["http://localhost:8000/cb"]}'

# 2. Authorise + exchange code for token (PKCE) — see oauth_pentest.md for full flow.
# 3. Create tenant + project.
curl -fsS -X POST http://localhost:8000/v1/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-ABS-Audience: abs-mcp" \
  -d '{"slug":"acme","name":"Acme Inc"}'

curl -fsS -X POST http://localhost:8000/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-ABS-Audience: abs-mcp" \
  -d '{"slug":"acme/handbook","tenant_slug":"acme","name":"Handbook"}'
```

## Step 5 — Index a document (3 minutes)

```bash
curl -fsS -X POST http://localhost:8000/v1/rag/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-ABS-Audience: abs-mcp" \
  -H "Content-Type: application/json" \
  -d '{"text":"ABS is a self-hosted AI orchestrator.","project_slug":"acme/handbook","title":"Handbook"}'
```

## Step 6 — Run a RAG query (2 minutes)

```bash
curl -fsS -X POST http://localhost:8000/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-ABS-Audience: abs-mcp" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is ABS?","project_slug":"acme/handbook","top_k":3}'
```

You should get a JSON response with cited chunks + a generated answer.

## What's next

- [Setup Guide](setup-guide.md) — full production install via Helm.
- [Architecture](architecture.md) — how the 13-layer stack fits together.
- [API Reference](api-reference.md) — every public endpoint.
- [Disaster Recovery](dr-runbook.md) — backup, restore, RTO/RPO targets.
- [Security Scope](security/scope.md) — pen-test scope and bug-bounty program.

## Trouble?

`docker compose logs backend` is your friend. Common gotchas in
[Troubleshooting](troubleshooting.md). If you're stuck, open a GitHub issue with
the trace ID from the LangFuse dashboard.

## Release notes (1.0.1)

- **First boot 60-90s is normal.** The backend health probe loops 6×15s
  while Cerbos pre-warms and BGE-M3 lazy-init kicks in. Don't kill the
  stack until `docker compose ps` shows every service `healthy`.
  Suggestion: `docker compose up -d --wait` (Compose v2.20+) to block
  the terminal exactly until that point.
- **Pre-DNS smoke test:** uncomment `tls internal` inside
  `Caddyfile.customer` so `curl -k https://abs.local/` works before
  pointing real DNS at the host. Re-comment the line before issuing
  real Let's Encrypt certs.
- **MCP / JSON-RPC remote smoke:** `/mcp/` rejects unknown `Host`
  headers with 421 by design. To curl-test from another machine, add
  the public hostname to `ABS_MCP_ALLOWED_HOSTS` in `.env`
  (`ABS_MCP_ALLOWED_HOSTS=abs.mycompany.com,localhost`). SDK clients
  derive the host from `ABS_PUBLIC_URL` automatically and need no
  extra config.
- **KVKK / GDPR self-service endpoints** live at `/me/data-export`,
  `/me/account/delete-request`, `/me/account/delete-confirm`,
  `/me/consents`, `/me/audit-log`. Caddy now routes every `/me/*` to
  the FastAPI backend (previously these fell into the Next.js 404 page
  on the customer compose file).
- **Canonical chat endpoint** is `POST /v1/chat/completions` (SSE). The
  former `/v1/chat`, `/v1/cascade/test`, `/v1/admin/cascade/breaker`
  paths are retired; use `/v1/admin/providers/status` for circuit
  inspection and `/v1/system/quota_status` for quota.
- **MCP tool inventory** is **122 tools** (one legacy entry was retired
  during the hexagonal restructure).
- **RAG ingest body is JSON** (`{"text": "...", "project_slug":
  "...", "title": "..."}` POST to `/v1/rag/ingest`). The old multipart
  `-F file=@...` example is retired; the endpoint never accepted
  multipart.
