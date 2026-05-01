# Automatia ABS — Self-host AI orchestration for Claude Code

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-409%20passing-brightgreen.svg)](#testing)
[![Lighthouse](https://img.shields.io/badge/lighthouse-100%2F100%2F100%2F100-brightgreen.svg)](docs/performance.md)
[![Tools](https://img.shields.io/badge/MCP%20tools-107-blue.svg)](docs/api-reference.md)

> **Run 100+ MCP tools and 6-provider cascade on your own server.** Pair your $20 Claude
> Pro plan with ABS to get RAG hybrid retrieval, quality pipelines, and tool
> orchestration that normally costs $1,000+/month — for **$299 one-time**.

🇬🇧 **English (default)** · 🇹🇷 [Türkçe](README.tr.md) · 🇪🇸 [Español](README.es.md)

---

## Why ABS

If you use **Claude Code** every day and pay $20 for Claude Pro, you have already paid
for the model. What you don't have is an orchestrator that:

- Routes calls across **6 providers** (Anthropic + Groq + Cerebras + Gemini +
  Cloudflare + Cohere) with circuit breaker.
- Ships **100+ MCP tools** out of the box (RAG hybrid, judge persona ML, fullstack
  developer mode, Türkçe quality pipeline, Stripe billing).
- Runs entirely on **your server**. No data leaves your VPS except the API calls
  *you* make to Anthropic.
- Is **billable software** — license JWT (RS256), Stripe checkout, customer portal,
  refund flow, demo countdown.

ABS is that orchestrator.

## Features at a glance

- ⚡ **6-provider cascade** with circuit breaker + cost dashboard.
- 🛠️ **107 MCP tools**: code review, test generation, RAG hybrid, judge ML, fullstack mode, billing.
- 🌍 **i18n out of the box** — English default, Türkçe + Español alternatives (24 email templates × 3 languages).
- 🔐 **sops + age vault** — Stripe / Anthropic / SMTP secrets stay encrypted at rest.
- 💳 **Stripe-ready** — checkout, webhook (idempotent), refund, customer portal.
- 📊 **Status page + Discord alerts** — public `/v1/status` JSON + auto-refresh HTML.
- 🚀 **Docker Compose deploy** — 15-minute installation on any Linux VPS.

## Quick install (15 minutes)

```bash
# Get a Linux VPS (Hetzner CX22 = $5/month works fine).
ssh root@your-server-ip
curl -fsSL https://raw.githubusercontent.com/automatiabcn/abs/main/infra/scripts/deploy_hetzner.sh | \
    bash -s -- --domain abs.your-domain.com --email admin@your-domain.com
# Browse to https://abs.your-domain.com/setup
```

The deploy script installs Docker, clones the repo, brings up the compose stack, and
fronts everything with Caddy (auto Let's Encrypt). Detailed setup:
[docs/setup-guide.md](docs/setup-guide.md).

## Pricing

| Plan | Price | Includes |
|---|---|---|
| **Self-Host Lifetime** | $299 one-time | Lifetime use + 1 year of updates + all features |
| **+ Maintenance** | +$49/year | Continuous updates + 48h priority email support |
| **Team Pack 5** | $1,196 | 5 seats, 20% off |
| **Team Pack 10** | $2,093 | 10 seats, 30% off |

**14-day no-questions refund.** Buy at [abs.automatiabcn.com](https://abs.automatiabcn.com/).

## How it works

1. **Install** ABS on your VPS via Docker Compose.
2. **Connect** Claude Code: `claude mcp add abs https://abs.your-domain.com/mcp`.
3. **Activate** the license JWT you received by email.
4. **Use** any of the 107 MCP tools from your normal Claude Code workflow.

ABS speaks the **Model Context Protocol** natively, so Claude Code can call ABS tools
the same way it calls built-in tools. There is no proxy, no man-in-the-middle —
prompts go from your machine to your ABS server to Anthropic, and stay private.

## Tech stack

- **Backend** — Python 3.13, FastAPI, SQLite + SQLModel, JWT RS256.
- **Frontend** — Next.js 15 (App Router), React 19, Tailwind 3.
- **MCP** — `mcp.server.fastmcp` (Anthropic-maintained Python SDK).
- **Vault** — Mozilla sops + age (4096-bit RSA optional).
- **Deploy** — Docker Compose + Caddy.
- **Tests** — pytest (409) + vitest (22) + Lighthouse (100/100/100/100).

Architecture: [docs/architecture.md](docs/architecture.md).
API reference: [docs/api-reference.md](docs/api-reference.md).

## Testing

```bash
# Backend
cd core/backend
.venv/bin/pytest -q

# Frontend
cd core/landing
npm test

# Lighthouse (production build)
npm run build && npm start &
npx lighthouse http://localhost:3000 --preset=desktop
```

## License

ABS is **Apache 2.0**. The closed premium add-ons (advanced RAG, team panel, future SaaS
mode) are bundled with every Self-Host Lifetime purchase. See [LICENSE](LICENSE).

## Community

- **Email** — [support@automatiabcn.com](mailto:support@automatiabcn.com) (48h SLA, 24h for Maintenance).
- **GitHub Discussions** — feature requests, ideas.
- **Discord beta** — invite-only for beta testers.
- **Status** — [status.abs.automatiabcn.com](https://status.abs.automatiabcn.com/).

## Contributing

We accept patches. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) before opening a PR. Security issues:
[SECURITY.md](SECURITY.md).

## Made by

[Automatia BCN](https://automatiabcn.com) · Barcelona, Spain · GDPR-compliant ·
14-day refund guarantee.
