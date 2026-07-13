# Automatia ABS — Architecture

This document defines the technical architecture of ABS: components, data flow, security, the customer workflow, technology choices and the scaling plan.

## 1. Overall Architecture

```
┌────────────── Customer Linux Server (Docker Compose) ────────────────────┐
│                                                                          │
│  Caddy (reverse proxy + automatic Let's Encrypt SSL)                     │
│   ├─ /                    → Landing redirect (if present)                │
│   ├─ /login               → Simple admin auth (licence key)              │
│   ├─ /panel               → HTML panel (7550 lines)                      │
│   ├─ /admin               → Next.js micro-app (optional)                 │
│   ├─ /api                 → Python orchestration backend                 │
│   ├─ /stream              → SSE (5 event types: metrics, orch, cohere,   │
│   │                         mcp-tools, quota-status)                     │
│   └─ /mcp                 → MCP endpoint (Claude Code connects here)     │
│                                                                          │
│  ABS Orchestrator (Python backend)                                       │
│   ├─ 75 MCP tools (abs_mcp_server port)                                  │
│   ├─ 5 hook modules (feature_nudge, delegate_nudge, plan_first,          │
│   │  rag_inject, enrichment)                                             │
│   ├─ 13 quality pipelines (qual-code, qual-tr, qual-analysis, ...)       │
│   ├─ Senior Judge (AST 60% + LLM 40%)                                    │
│   ├─ Workflow durability (SQLite checkpoint)                             │
│   ├─ Symbol-aware RAG (10K symbols + 13K callsites)                      │
│   ├─ Cache hit counter                                                   │
│   └─ Cohere threshold alert                                              │
│                                                                          │
│  SQLite DB (MVP, single-user)                                            │
│  age/sops encrypted secrets volume (API keys)                            │
│  Ollama container (optional, local LLM fallback)                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
            │
            ├─── Developer CLI (Claude Code) ── local machine
            │    `claude mcp add abs https://abs.domain.com/mcp`
            │
            └─── Web browser (panel) ── any device
                 https://abs.domain.com/panel
```

## 2. Components

| Component | What it does | Source |
|---|---|---|
| Caddy | Reverse proxy, automatic HTTPS (Let's Encrypt), forward_auth | Upstream |
| Python Orchestrator | The core logic (MCP + hooks + pipelines + provider chain + judge + RAG) | Built-in |
| SQLite DB | Workflow state + judge log + cache metadata + audit | Native |
| age/sops | Encrypted secrets at rest (API keys, licence key) | Native |
| Ollama | Local LLM fallback, optional (fast when a GPU is present) | Upstream |
| HTML panel | 7550 lines, served behind the auth proxy | Built-in |
| Next.js admin | Optional micro-app — licence management, provider config UI | New |

## 3. Access and Endpoints

| URL | Who reaches it | Purpose |
|---|---|---|
| `https://abs.domain.com/panel` | Admin (after login) | Dashboard, cosmos, widgets |
| `https://abs.domain.com/admin` | Admin | Licence, providers, settings |
| `https://abs.domain.com/api/*` | Internal (panel, CLI) | REST API |
| `https://abs.domain.com/stream` | Internal (panel) | SSE real-time events |
| `https://abs.domain.com/mcp` | Claude Code, custom CLI | MCP endpoint |
| `https://abs.domain.com:443` | Caddy, all traffic | Automatic SSL |

## 4. Provider Chain — 7 Layers of Protection

```
1. Abstraction Layer
   Customer code: model="fast-reasoning"
   ABS config: model_alias_map → provider + model_id
   (When a provider changes, the JSON is updated — the code is untouched)
         ↓
2. Circuit Breaker
   5 errors / 1 min → "open" state (60s)
   Half-open: test → full recovery, or open again
         ↓
3. Provider Chain Fallback
   Groq → Cerebras → CloudFlare → Gemini → Anthropic
   (the order is set in the customer's config)
         ↓
4. Semantic Cache (SHA-256 prompt hash, 5 min TTL)
   Provider slow/down → answer from the cache
         ↓
5. Health Monitor (on the customer's server, 60s ping)
   Live status in the panel: green/amber/red
         ↓
6. Central Watchdog (vendor side, once a day)
   Provider pricing + changelog + status + synthetic test
         ↓
7. Update Channel (release-based)
   provider_configs/*.yaml updates ship with the release
```

Detail: `docs/operations.md` § 2-5.

## 5. Security

| Layer | Mechanism |
|---|---|
| **API key storage** | age/sops encrypted at rest. Never held in memory as cleartext |
| **Transport** | Caddy + automatic Let's Encrypt HTTPS |
| **Auth** | Admin login (licence key, JWT session) |
| **Audit log** | Who added or changed which key, and when |
| **Data residency** | Customer code stays on the ABS server; it goes to the provider API under the customer's own account |
| **Licence verification** | JWT RS256 signature, no phone-home, works offline |
| **Secret rotation** | One click from the panel |

**Important:** **no customer data ever reaches our cloud server.** Only the licence key verification signal (hash-based) reaches our watchdog. Prompts and code go straight from the customer's server to the provider APIs.

## 6. Customer Workflow

**Installation:**
1. The customer rents a Linux server (Hetzner, DO, AWS, etc.)
2. `curl -fsSL https://get.abs.automatiabcn.com/install.sh | bash`
3. Docker, Docker Compose and the ABS containers are installed (~5 min)
4. Open `https://server-ip:8443/setup` in a browser
5. A 6-step wizard (admin + licence + domain/IP + Anthropic key + optional providers + test)

**Daily use:**
1. The developer runs `claude mcp add abs https://abs.company.com/mcp` on their own machine
2. They open `claude` in a terminal
3. They send a prompt → Claude Code forwards it to ABS over MCP
4. ABS goes **abstraction layer** → **circuit breaker** → **provider chain** → provider
5. The answer comes back from ABS to Claude Code
6. The log, metrics and widgets in the panel update

**Monitoring:**
1. The admin watches provider status from the panel
2. The audit log is visible
3. Budget tracker (Anthropic API usage)
4. Judge scores, workflow states

## 7. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Reverse proxy | **Caddy** | Automatic HTTPS, simple Caddyfile |
| Backend | **Python 3.11+** | Matches the orchestration code |
| Database | **SQLite (MVP)** → **PostgreSQL (Phase 2+)** | Simple for single-user; multi-organisation later |
| Auth | **Lucia** (MVP) → **Authentik** (Phase 2+) | MVP is single-user; growth needs multi-user |
| Admin UI | **Vanilla JS + Alpine.js** or **SvelteKit** (in addition to Next.js) | Lightweight, consistent with the existing panel style |
| Secrets | **age** + **sops** | Modern, simple, offline |
| Container | **Docker Compose** | One file, identical in dev and prod |
| LLM fallback | **Ollama** (Linux, instead of Apple Silicon MLX) | Cross-platform |

## 8. Scaling Approach (MVP → Growth)

### MVP (Months 1-3): Single-User Self-Host
- 1 installation = 1 user
- SQLite + Lucia + a single admin
- One Docker Compose file
- Customers: 5-20
- Ceiling: one server per user

### Growth (Months 3-6): Managed Cloud Beta
- 3-5 beta customers on our servers
- PostgreSQL, one schema per organisation
- A simple admin dashboard (on our side)
- Automatic backup + monitoring
- $79/month (beta pricing)

### Scale (Months 6-12): Managed Cloud, Full Launch
- 20+ customers
- PostgreSQL RLS (row-level security)
- Authentik with multi-organisation support
- Not Kubernetes (overkill for a solo operator) — VPS + Caddy + Docker
- 99.5%+ uptime SLA

### Enterprise (Year 2+): VPC / On-Prem Dedicated
- A dedicated ABS instance inside the customer's own VPC
- Managed by Automatia (optional)
- SOC 2 Type II preparation
- Custom SLA
