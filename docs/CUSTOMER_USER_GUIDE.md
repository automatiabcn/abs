# Automatia ABS — Customer User Guide

> **Self-hosted AI orchestrator. Automate the chaos on your own server.**
>
> Version: 1.0 · Last updated: 2026-05-09 · License: BSL 1.1

---

## Contents

1. [Welcome](#welcome)
2. [Buying ABS](#1-buying-abs)
3. [Preparing the VPS](#2-preparing-the-vps)
4. [Installing ABS](#3-installing-abs)
5. [First configuration (Setup Wizard)](#4-first-configuration-setup-wizard)
6. [Provider API keys](#5-provider-api-keys)
7. [Your first chat](#6-your-first-chat)
8. [RAG knowledge base](#7-rag-knowledge-base)
9. [Quality Pipelines](#8-quality-pipelines)
10. [Workflow Builder](#9-workflow-builder)
11. [Knowledge Graph](#10-knowledge-graph)
12. [Plugin Marketplace](#11-plugin-marketplace)
13. [Admin settings](#12-admin-settings)
14. [License and refunds](#13-license-and-refunds)
15. [Troubleshooting](#14-troubleshooting)
16. [Legal notices and trademarks](#legal-notices-and-trademarks)

---

## Welcome

ABS (Automation Backbone System) is an AI orchestrator that runs on your own server. It gives you 100+ MCP tools, a router across 6 providers (Anthropic, Groq, Cerebras, Gemini, Cloudflare, Cohere) and hybrid RAG as a single AI infrastructure.

**Usage rights:** As a customer you may run ABS in **production** on your own server. The BSL 1.1 license converts to Apache 2.0 automatically after 4 years (2030-05-07).

**Scope of this guide:** the 30-minute path from purchase to a running install, plus basic usage. For advanced topics see [docs/api-reference.md](api-reference.md) and [docs/runbooks/](runbooks/).

---

## 1. Buying ABS

### 1.1 Product page

[automatiabcn.com/products/abs](https://automatiabcn.com/products/abs) — three tiers:

| Tier | Price | Includes |
|------|-------|----------|
| Self-Host | $299 (one-off) | 1 seat · 1 deployment · email support (48h) |
| Team 5 | $1,196/year | 5 seats · priority email (24h) · onboarding call |
| Team 10 | $2,093/year | 10 seats · 24h SLA · priority support line |

> Every tier comes with a 14-day no-questions-asked refund. See [Section 13](#13-license-and-refunds).

### 1.2 Payment

The "Buy now" button takes you to a secure payment page (3D Secure supported). The form asks for:

- Email (your license is sent to this address — enter it correctly)
- Card number, expiry, CVC
- Cardholder name and country

### 1.3 Confirmation

Once payment is approved you see a "Thanks for your payment" page, and:

1. A **welcome email** (order summary + the 7 install steps) reaches that address within about a minute.
2. A **notification** goes to the Automatia BCN team.
3. Your **license JWT** is minted by the Automatia BCN team and sent in a separate email within 24 hours.

> **No email?** Check your spam folder. If it is still missing, write to `info@automatiabcn.com` with your order ID.

---

## 2. Preparing the VPS

ABS runs on any Linux x86_64 / ARM64 server. **Minimum:** 2 vCPU, 4 GB RAM, 40 GB SSD. Ubuntu 22.04 LTS is recommended.

### 2.1 Suggested providers

| Provider | Plan | Monthly | Regions |
|----------|------|---------|---------|
| Hetzner Cloud | CPX22 (AMD, 2 vCPU, 4 GB, 80 GB NVMe) | ≈ €4.99 | Germany/Finland/USA |
| DigitalOcean | Basic 4GB | ≈ $24 | Frankfurt/Amsterdam/NYC |
| Linode (Akamai) | Linode 4GB | ≈ $24 | global |
| Vultr | Cloud Compute 4GB | ≈ $24 | global |
| Your own server | Bare-metal / Proxmox VM | — | on-premises |

> This list is guidance only; we do not resell any of it. Product names are trademarks of their respective companies.

### 2.2 Creating the server (general steps)

1. Create a new server in your provider's web panel: 2 vCPU + 4 GB RAM minimum.
2. Image: **Ubuntu 22.04 LTS**.
3. Upload your SSH key (if you do not have one, create it with `ssh-keygen -t ed25519 -C "abs-customer"` and paste the public key into the panel).
4. When the server is up, note its **public IPv4** address.
5. Connect over SSH: `ssh -i ~/.ssh/abs-customer root@<IPv4>`.

> **A domain is optional.** Without one, use the `<IPv4>.sslip.io` form (for example `203-0-113-7.sslip.io`) and Caddy will issue a Let's Encrypt certificate automatically. You do not need to add a DNS record.

---

## 3. Installing ABS

### 3.1 Install Docker

On Ubuntu 22.04:

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2 docker-buildx
systemctl enable --now docker
docker --version          # must be 24+
docker compose version    # must be v2.20+
```

### 3.2 Get the ABS repository

```bash
git clone https://github.com/automatiabcn/abs.git /opt/abs
cd /opt/abs
```

> The repository is public (BSL 1.1). You can read the source, but commercial use requires a license.

### 3.3 Environment file (.env)

```bash
cp .env.example .env
nano .env
```

Fill in these values (the welcome email has examples):

```env
ABS_LICENSE_KEY=<license-jwt-from-email>
ABS_PUBLIC_HOSTNAME=<domain or 203-0-113-7.sslip.io>
ABS_PUBLIC_URL=https://${ABS_PUBLIC_HOSTNAME}
ABS_ACME_EMAIL=<address-for-certificate-notices>
ABS_VAULT_KEY=$(openssl rand -base64 32)
ABS_VERSION=1.0.0-rc4
ANTHROPIC_API_KEY=sk-ant-...   # you will get this in Section 5
```

### 3.4 Start the stack

```bash
docker compose up -d
docker compose ps          # 4 containers must be "healthy" (≈30 s)
```

On first start the backend pulls about 1.3 GB from GHCR.

### 3.5 Health check

```bash
curl -s https://${ABS_PUBLIC_HOSTNAME}/healthz
# expected response: {"status":"ok","service":"abs-backend"}
```

> On first boot Caddy issues the Let's Encrypt certificate within about 30 s. Your first browser request may wait for that.

---

## 4. First configuration (Setup Wizard)

Open `https://<ABS_PUBLIC_HOSTNAME>/setup` in your browser. A 6-step wizard starts.

### Step 1 — Admin account

Define the main account that signs in to the panel:
- Email (for example `admin@yourcompany.com`)
- Password (at least 8 characters)

### Step 2 — License

Paste the JWT token from your email, then click "Activate". The backend verifies the signature.

### Step 3 — Domain

Pick a mode:
- **IP**: a one-off smoke test (`<IP>.sslip.io`).
- **Domain**: your own domain (recommended).

SSL mode: **ACME** (Let's Encrypt) is the default.

### Step 4 — Anthropic API key

Create an API key in the Anthropic Console ([console.anthropic.com](https://console.anthropic.com/)) and paste it in. The key must start with `sk-ant-`. For the full provider sign-up flow see [Section 5](#5-provider-api-keys).

### Step 5 — Other providers (optional)

Additional providers for the router:
- Groq (`gsk_...`)
- Gemini / Google AI (`AIza...`)
- Cerebras (`csk-...`)
- Cohere (`...`)
- Cloudflare Workers AI (Account ID + API Token)

Whichever you enter is added to the fallback chain.

### Step 6 — Test

Shows the ping test result for each configured provider. When they PASS, the wizard completes.

---

## 5. Provider API keys

You get provider API keys **from your own accounts**, and those providers bill **your own accounts**. ABS takes no commission.

### 5.1 Anthropic Claude (recommended, primary)

1. [console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys → "Create Key"
2. Name: `abs-orchestrator-prod`
3. Workspace: your default
4. The key is shown once — store it somewhere safe (`sk-ant-api03-...`)
5. Paste it into Setup Wizard Step 4

> **Cost:** the Claude API is billed per use (by token). The $20/month Pro plan covers the API bill.

### 5.2 Groq (free tier, fast)

1. [console.groq.com](https://console.groq.com/keys) → "Create API Key"
2. The key starts with `gsk_`
3. Setup Wizard Step 5

> The free tier is excellent for high speed (Llama 3.3 70B). Rate limit: 30 requests/minute.

### 5.3 Google Gemini (free tier)

1. [aistudio.google.com](https://aistudio.google.com/app/apikey) → "Create API key"
2. The key starts with `AIza`
3. Setup Wizard Step 5

> The Gemini 2.5 Flash free limit is generous. The Pro plan is optional.

### 5.4 Cerebras (very fast)

1. [cloud.cerebras.ai](https://cloud.cerebras.ai/) → API Keys
2. The key starts with `csk-`
3. Setup Wizard Step 5

> The Cerebras WSE-3 answers in milliseconds rather than seconds.

### 5.5 Cohere (free trial)

1. [dashboard.cohere.com](https://dashboard.cohere.com/api-keys) → "API Keys"
2. You start with a trial key
3. Setup Wizard Step 5

### 5.6 Cloudflare Workers AI

1. [dash.cloudflare.com](https://dash.cloudflare.com/) → AI → Workers AI
2. Account ID: copy it from the bottom-right corner
3. API Token: My Profile → API Tokens → Workers AI Read template

> **Trademark note:** Anthropic, Claude, Groq, Gemini, Cerebras, Cohere and Cloudflare are trademarks of their respective companies. ABS provides the customer-side integration with these services; that is not an official partnership or endorsement.

---

## 6. Your first chat

Sign in to the panel at `https://<domain>/login` with the admin email and password you set in the Setup Wizard.

### 6.1 Start a chat

In the left nav go to **Chat** → New chat → type your message. The answer comes back through the provider router.

The `meta` block shows which provider answered (`provider: anthropic`), the token count and the latency.

### 6.2 Choosing a pipeline

A standard chat uses the `auto_direct` pipeline. The advanced pipelines are:

| Pipeline | Purpose | Time |
|----------|---------|------|
| `auto_direct` | Single model, fast answer | ~1-3 s |
| `qual_code` | Code generation (generate → verify → fix) | ~3-8 s |
| `qual_tr` | Turkish text (generate → check → polish) | ~3-8 s |
| `qual_translate` | Translation (translate → back-translate → verify) | ~3-8 s |
| `qual_analysis` | 3-perspective analysis + synthesis | ~10-15 s |
| `race_code` | 3 models race, the fastest wins | ~2-5 s |

Each pipeline appears as a card in the UI. Click it, write your prompt, then run it.

---

## 7. RAG knowledge base

Left nav → **RAG Knowledge Base**. The page shows the document count, chunk count, total size and the top-K setting.

### 7.1 Uploading documents

PDF · MD · TXT · DOCX (≤ 25 MB). Drag and drop, or click "Choose file". ABS chunks and indexes the document automatically with BGE-M3 dense embeddings.

### 7.2 Querying

Type a question into the query box in any language and click "Run query". You get the top-K results (5 by default) with their scores.

> **Data security:** the RAG index stays entirely on your server (ChromaDB + Qdrant). No document content is sent to Anthropic or any other provider — only your query plus the retrieved chunks go to the LLM, so it can compose an answer.

---

## 8. Quality Pipelines

Not a single model but a chain: generate → verify → fix, or a race where the fastest answer wins.

There are 9 pipelines. See [Section 6.2](#62-choosing-a-pipeline) for the details.

> The pipelines use Anthropic and the other providers in parallel; output quality goes up compared with a single model while cost stays in check (when Claude is down, Groq takes over).

---

## 9. Workflow Builder

Describe a workflow in plain language and ABS turns it into an n8n-compatible node graph.

### 9.1 Creating a workflow

1. Describe the workflow in the "Describe your workflow" box (for example, "Classify incoming Gmail messages and draft a reply to anything tagged sales").
2. **Synthesize** → ABS generates the workflow JSON with an LLM.
3. Edit it → you can add a human-approval (HITL) step.
4. **Dry run** → simulate it.
5. **Save** → it is added to your organisation's workflow list and can be exported to n8n.

> The estimated cost per run is shown in the panel.

---

## 10. Knowledge Graph

A company graph built on Neo4j 5: Person, Org, Project and Ticket nodes, plus WORKS_AT, OWNS, MANAGES and ASSIGNED_TO relationships. The page gives you the schema, saved queries, a Cypher editor and natural-language query.

### 10.1 Cypher editor

Read-only users can run only MATCH/RETURN. For example:

```cypher
MATCH (p:Person)-[:WORKS_AT]->(o:Org {name:"Acme"})
RETURN p.name, p.email LIMIT 25
```

### 10.2 Natural-language query

"Find everyone who works at Acme" → ABS generates the Cypher → you run it.

> Neo4j and Cypher are trademarks of Neo4j, Inc. Use is subject to the Neo4j Community Edition license.

---

## 11. Plugin Marketplace

Left nav → **Marketplace**. The ABS ecosystem: LLM providers, RAG sources, MCP tools and workflow templates — for example Slack Receiver, Gmail Archiver, Linear Bridge, Notion Sync and Postgres Mirror.

### 11.1 Installing a plugin

1. Click **Install** on the plugin card → a "Review permissions" modal opens.
2. It lists network egress, mounts, secrets, resource usage (CPU/RAM) and the scope within your organisation.
3. Tick the confirmation box → **Approve & Install**.
4. The plugin starts inside a sandbox cgroup and the install is written to the audit log.

### 11.2 Filtering

Use the category chips at the top (LLM Provider / RAG Source / MCP Tool / Workflow Template) and the search box.

> Slack, Gmail, Linear, Notion and Postgres are trademarks of their respective companies. The plugins use the customer-side APIs of those services.

---

## 12. Admin settings

Left nav → **Settings**. Seven sub-tabs:

| Tab | Contents |
|-----|----------|
| General | Organisation name, slug, domain, SSL |
| License | Active license status, JWT renewal |
| Providers | Provider order, mock mode, "Configure" for each provider |
| Webhooks | Slack, email and Discord webhook URLs |
| Alerts | Quota alert threshold, p95 latency SLO |
| Branding | Logo, favicon, brand colour, login message |
| Security | Magic-link lifetime, session length, audience checks |

> Every change is isolated to your organisation and written to the audit log.

---

## 13. License and refunds

### 13.1 14-day no-questions-asked refund

Self-Host: if you ask for a refund within 14 days you get the full amount back, your license is revoked in the Cloudflare Worker, and your ABS instance starts rejecting chat calls at the next heartbeat (≤60 s).

**How to get a refund:**

1. Email your order ID to `info@automatiabcn.com`.
2. The Stripe refund starts within 5 business days (it can take another 5-10 business days to reach your card, depending on your bank).
3. Your license token is revoked; the backend moves to `license_state.valid = False`.
4. New chat calls are rejected with 403. Your local configuration (admin password, RAG index) is left intact.

### 13.2 Renewal (Maintenance Pack)

After 12 months, the **optional** $49/year Maintenance Pack keeps updates and email support running. If you skip it, ABS keeps running on its current version indefinitely, but you lose access to new image updates.

### 13.3 Moving your license

Hardware fingerprint binding is **optional** (CJ-005). If no fingerprint was assigned when the license was minted (`machine_fp: null`), you can move the license to another machine; the Cloudflare Worker records the new IP/fingerprint on activation.

---

## 14. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker compose up -d` says "exec format error" | The image is multi-arch from rc4 on — the older tags (rc1/rc2) do not run on Apple Silicon. Set `ABS_VERSION=1.0.0-rc4`. |
| Caddy 502 / TLS error | Ports 80 and 443 must be open in the firewall (Let's Encrypt HTTP-01). Run `ufw allow 80,443/tcp`. |
| Setup Wizard says "License signature invalid" | The license signature may not match the public key in the container; contact the Automatia BCN team. |
| Chat returns "license_invalid" 403 | The heartbeat saw the license as revoked. Check your license email or renew it. |
| RAG query returns nothing | The document is not indexed yet. Run `docker compose logs backend` and wait for the "embedding done" message. |
| Knowledge Graph returns "Internal Server Error" | The Neo4j initialisation for your organisation may be incomplete. Try `docker compose restart`, then contact Automatia BCN support. |
| Email never arrived | Check your spam folder; if you run your own SMTP relay, check Settings → Webhooks → Email alerts. |
| High RAM usage | The Whisper/TTS models are optional; turn them off with `ABS_DISABLE_TTS=1` in `.env`. |

> If you cannot find an answer, email `info@automatiabcn.com` (24h response) or use your own support channel.

---

## Legal notices and trademarks

- **Automatia ABS™** is a trademark of Automatia BCN.
- **Anthropic®, Claude®, Cohere®, Cerebras®, Groq®, Gemini™, Cloudflare®, Stripe®, Hetzner®, DigitalOcean®, Linode®, Vultr®, Slack®, Gmail™, Linear®, Notion®, PostgreSQL®, Neo4j®, Docker®, Caddy®, Let's Encrypt®** are trademarks of their respective companies. The references in this guide are customer-side integration information only; they do not imply an official partnership or endorsement.
- Provider API usage is billed **to the customer's own account**. Automatia BCN takes no share of those charges and does not invoice them.
- ABS is distributed under the BSL 1.1 license (see the `LICENSE` file). It converts to the Apache License 2.0 automatically on 2030-05-07.
- Under GDPR (and Turkey's KVKK) you process personal data **on your own server**, as the data processor. Automatia BCN has no access to that data. For retention periods see Settings → Security.

---

**Last updated:** 2026-05-09 · v1.0  
**Contact:** info@automatiabcn.com  
**Source:** [github.com/automatiabcn/abs](https://github.com/automatiabcn/abs)  
**Made in Barcelona** — *Automate the chaos*
