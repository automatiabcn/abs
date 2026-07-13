# FAQ — frequently asked questions

15 short questions and answers. Each one points you to the page with the full story.

## Product

### 1. What is ABS?
Self-hosted AI orchestration. It extends Claude Code with 100+ MCP tools, a
6-provider chain (Anthropic + Groq + Cerebras + Gemini + Cloudflare + Cohere),
hybrid RAG and a Turkish quality pipeline. It runs on your own server and you pay
per use.

### 2. Does this comply with the Anthropic TOS?
Yes. ABS uses Anthropic's pay-per-use API (not Pro-subscription OAuth). You
connect with your own API key, your prompts go to Anthropic, and no data is sent
to any ABS server.

### 3. Why ABS when Cursor / Cline / Aider exist?
ABS is not an IDE plugin — it is a self-hosted network. You use it alongside those
IDEs. The 6-provider chain, circuit breaker, token tracking, hybrid RAG and the
Turkish quality pipeline come in one product.

## Technical

### 4. What hardware do I need?
1 vCPU, 2 GB RAM, 20 GB disk. A Hetzner CX22 ($5/month) or a similar VPS is enough.
For production scale (>10 users), 2 vCPU and 4 GB RAM are recommended.

### 5. Which database?
SQLite + WAL. Four tables in total: `licenses`, `webhook_events`, `email_queue`,
plus the durability stores (workflow_state, judge_log, rag_chroma).
The Postgres adapter is deferred to 022+.

### 6. How does the vault work?
Mozilla sops + age — your Stripe key, Anthropic key and SMTP password are always
encrypted on disk. At boot the backend decrypts them into the in-memory settings
object. The age master key lives on a separate read-only volume — a trust boundary
the backend cannot write to.

### 7. Which LLM models are supported?
Anthropic Claude (Opus, Sonnet, Haiku), Groq (GPT-OSS 120B, Qwen3 32B, Kimi K2,
Llama 4 Scout, Llama 3.x), Cerebras Llama, Gemini 2.5 Pro/Flash, Cloudflare
Workers AI (10+ models), Cohere Command R, and Apple Silicon MLX (Phi-3, Llama3-8B).

## License and billing

### 8. How does the license work?
A JWT signed with RS256; the public key is embedded in the server and there is no
online check. If you lose your license, get it again from the panel or from your
purchase email.

### 9. Is there a demo?
Yes — a new install runs a 14-day demo automatically. Every MCP tool works during
the demo. When it expires, the tools are blocked if `mcp_require_license=true`.

### 10. What is the refund policy?
14 days, no questions asked. Self-service through the Stripe Customer Portal. As
soon as the refund is approved, the license is deactivated with `revoked_at`.

### 11. Annual or one-off?
Self-Host Lifetime $299 — ONE-OFF. Maintenance $49/year is optional.
The annual subscription tier is deferred to 022+.

## Data and security

### 12. Does my data go to Anthropic?
Only the prompts in your Claude API calls. ABS is not a proxy — you make the
request from your own server and Anthropic answers it. No customer data reaches
Automatia BCN servers.

### 13. Is it GDPR compliant?
Yes. The data controller is Automatia BCN (Barcelona). User data stays on the
server of whoever runs ABS; only payment data sits with Stripe (PCI-DSS). For your
rights under EU Articles 15-22, write to `privacy@automatiabcn.com`.

### 14. Is it open source?
The core (`core/backend`, `core/landing`) is Apache 2.0. The premium add-ons
(advanced RAG, team panel, the future SaaS mode) are closed source. Self-Host
Lifetime owners get the premium add-ons too.

## Operations

### 15. How do updates arrive?
`docker compose pull && docker compose up -d`. ABS verifies the update channel
signature (014). Self-Host Lifetime includes 1 year of free updates.
After that it is Maintenance at $49/year.

---

More questions? `support@automatiabcn.com` or GitHub Discussions.
Full details: [Setup Guide](setup-guide.md), [API Reference](api-reference.md).
