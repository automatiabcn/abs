# Settled Design Decisions

_Last updated: 2026-04-23_

## STRATEGIC DECISIONS (2026-04-23)

### 1. Target Customer: **Individual Self-Host** (companies of 10-50 people)

**Revision:** ~~a central multi-organisation server~~ → **each user runs their own installation.** A company buys 10 separate licences (a volume discount is possible).

**Why:** it removes a lot of engineering (no multi-organisation database, auth or RBAC), cutting the MVP from 6 weeks to 2-3 weeks.

### 2. Brand: **Automatia ABS**

- Domain: `abs.automatiabcn.com` (subdomain — marketing and technical independence)
- Main site: `automatiabcn.com` → "Our Products" → link to ABS
- Logo: the existing Automatia logo

### 3. Operations: **Solo Operator + the ABS System = a Working Team**

Marketing line: "We and the system work as one team. Dogfooding — we are the first users of this product."

### 4. API Key Model: **The Customer's Own Keys**

Anthropic + 5 free providers (Groq, Cerebras, CloudFlare, Gemini, Cohere). Keys are entered in the web setup wizard, encrypted at rest with `age`/`sops`, and rotated from the panel.

**Onboarding order:**
- Required: Anthropic API key
- Recommended: Groq + Gemini (free)
- Optional: Cerebras + CloudFlare + Cohere

### 5. Feature Parity: **The Full Set, and More**

Everything the orchestration system already has (75 MCP tools + 5 hooks + 13 pipelines + RAG + judge + workflow + panel), plus new additions (optional multi-user auth, audit log).

### 6. Revenue: **One-time $299 + Optional Maintenance**

- **$299 one-time** = a lifetime licence + 1 year of updates
- **$49/year** optional maintenance (updates and support continue)
- If it lapses: the version you have keeps working forever, but you get no new features
- **No subscription** (a deliberate choice)

### 7. Distribution Model: **Phased Dual Distribution**

- **Phase 1 (months 1-3):** self-host lifetime sales come first
- **Phase 2 (months 3-6):** Managed Cloud beta at $79/month (3-5 customers)
- **Phase 3 (month 6+):** Managed Cloud general availability

### 8. Team Pack

- 5 seats: $299 × 5 × 0.8 = **$1196** (20% off)
- 10 seats: $299 × 10 × 0.7 = **$2093** (30% off)
- 25+ seats: custom quote

### 9. Free Tier: **None**

- 14-day demo mode (full feature set)
- When the demo ends, the system stops
- Overseas companies: a private beta (free)

### 10. Payment: **Stripe Checkout (on the automatiabcn.com account)**

- Stripe directly rather than Lemon Squeezy (no merchant of record needed; the Automatia entity exists)
- Webhook → licence key generator (JWT-signed, self-implemented for the MVP)

---

## TECHNICAL DECISIONS FROM RESEARCH (2026-04-23)

### 11. Minimum System Requirements

- **2 vCPU / 4 GB RAM / 20 GB SSD**
- GPU optional (for the local Ollama fallback)
- Ubuntu 22.04+ / Debian 12+ / any Docker-compatible Linux

### 12. SSL + Domain (a choice, not a requirement)

**The setup wizard offers two options:**
- **A) IP + port** — LAN only, no domain, HTTP (fastest to start)
- **B) Your own domain + HTTPS** — professional; Caddy handles Let's Encrypt automatically
  - The customer adds an A record in DNS (e.g. `abs.mycompany.com` → server IP)
  - They pass `DOMAIN=abs.mycompany.com` at install time
  - Caddy has SSL ready in 60 seconds

### 13. Demo Mode

- 14 days, full feature set
- A countdown banner in the panel
- When it expires: a "Your licence has expired, please buy" screen — the system stops working

### 14. What Happens When Maintenance Lapses

- The last version you downloaded keeps working forever
- New updates are locked ("Maintenance expired, renew for $49/year")
- Adding a new provider (e.g. Groq v2) will not work, because the config updates no longer arrive

### 15. Provider Down UI

- A **banner** in the panel (green = OK, amber = degraded, red = down)
- Automatic fallback down the provider chain (silent)
- Admin notification: "Groq has been failing for 15 minutes, falling back to Cerebras"

### 16. RAG Indexing UX

- A **"Projects"** page in the panel
- "Add Project" → enter a path → indexing starts automatically
- Progress bar + log (symbol count, file count)
- Optional git hook (auto-reindex on commit)

### 17. Update Mechanism

- `docker-compose pull && docker-compose up -d`
- An "Update available v1.x.y" notification in the panel
- An optional one-click automatic update button
- A manual migration script for breaking changes

### 18. Refund Policy

- **14 days, no questions asked**
- One-click refund in Stripe
- After that: case by case (rare)

### 19. Privacy Policy (Transparent to the Customer)

The key statement:
> "ABS forwards customer prompts and code fragments directly to Anthropic and to the other LLM providers you select. This is inherent to using the Claude API. Code and prompt data never reach our server — it only receives a licence verification signal. The customer is bound by the terms of service of their own Anthropic / Groq / Gemini and other accounts."

---

## OPERATIONS DECISIONS (2026-04-23)

### 20. ABS Central Watchdog — Runs on Our Server

- A Python cron service under `abs.automatiabcn.com/watchdog/`
- Daily 06:00 scan: provider pricing + changelog + status JSON + community
- A change → Discord/email alert → we start preparing a release
- A Hetzner VPS at $5-10/month is enough

### 21. Provider Config Update Channel

- Our repository: the `infra/provider-configs/` directory
- The `*.yaml` files can be updated with every release
- The new config takes effect when the customer takes an update
- A critical change (a deprecated provider) → hotfix release + customer email

### 22. The 7-Layer Protection Architecture

1. **Abstraction layer** (model aliases such as `fast-reasoning`)
2. **Circuit breaker** (5 errors → open, half-open after 60s)
3. **Provider chain fallback** (Groq → Cerebras → CF → Gemini → Anthropic)
4. **Semantic cache** (5 min TTL; answer from cache when a provider is slow or down)
5. **Health monitor** (on the customer's server, a 60s provider ping)
6. **Central Watchdog** (our side, a daily changelog scan)
7. **Update channel** (release-based config updates)

Detail: `docs/operations.md`

---

## SKIPPED / DEFERRED (not now)

- **A deep legal review of the Anthropic TOS** — important, but not a blocker right now (commercial terms for API keys are legally fine)
- **The AES-256 encryption profile package** — on the roadmap
- **SOC 2 / ISO 27001** — after 100+ customers
- **Multi-language** (TR/EN is enough for now)
- **An affiliate/referral programme** — after the MVP
- **A DPA template** — when an enterprise customer asks for it
- **A public Kubernetes Helm chart** — later
