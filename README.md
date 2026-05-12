# Automatia ABS — Self-hosted AI orchestrator

> Part of the [Automatia BCN](https://automatiabcn.com) product family · Made in Barcelona

[![License: BUSL-1.1](https://img.shields.io/badge/License-BUSL--1.1-orange.svg)](LICENSE)
[![CI](https://github.com/automatiabcn/abs/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/automatiabcn/abs/actions/workflows/ci.yml)
[![CodeQL](https://github.com/automatiabcn/abs/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/automatiabcn/abs/actions/workflows/codeql.yml)
[![Tests](https://img.shields.io/badge/tests-2065%20passing-brightgreen.svg)](#testing)
[![Lighthouse](https://img.shields.io/badge/lighthouse-100%2F100%2F100%2F100-brightgreen.svg)](docs/performance.md)
[![Tools](https://img.shields.io/badge/MCP%20tools-123-blue.svg)](docs/api-reference.md)
[![Made in Barcelona](https://img.shields.io/badge/Made%20in-Barcelona%20%F0%9F%87%AA%F0%9F%87%B8-blue.svg)](https://automatiabcn.com)

> **Automate the chaos — on your own server.** Pair your Anthropic API key (or Claude
> Pro plan) with ABS to get 100+ MCP tools, a 6-provider cascade, RAG hybrid retrieval,
> and quality pipelines that normally cost $1,000+/month — for **$299 one-time**.

🇬🇧 **English (default)** · 🇹🇷 [Türkçe](README.tr.md) · 🇪🇸 [Español](README.es.md)

---

## Why ABS

If you pay for Anthropic Claude (Pro plan or pay-as-you-go API), you have already paid
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
- 🛠️ **123 MCP tools**: code review, test generation, RAG hybrid, judge ML, fullstack mode, billing.
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
4. **Use** any of the 123 MCP tools from your normal Claude Code workflow.

ABS speaks the **Model Context Protocol** natively, so Claude Code can call ABS tools
the same way it calls built-in tools. There is no proxy, no man-in-the-middle —
prompts go from your machine to your ABS server to Anthropic, and stay private.

## Tech stack

- **Backend** — Python 3.13, FastAPI, SQLite + SQLModel, JWT RS256.
- **Frontend** — Next.js 15 (App Router), React 19, Tailwind 3.
- **MCP** — `mcp.server.fastmcp` (Anthropic-maintained Python SDK).
- **Vault** — Mozilla sops + age (4096-bit RSA optional).
- **Deploy** — Docker Compose + Caddy.
- **Tests** — pytest (2065) + vitest (53) + Playwright (41) + Lighthouse (100/100/100/100).

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

ABS is licensed under the **Business Source License 1.1** (SPDX: `BUSL-1.1`).

- **Free use** — development, evaluation, internal testing on non-production environments. No fee, no permission required.
- **Production use** — requires a Commercial License from [Automatia BCN](https://automatiabcn.com). See [docs/customer-agreement.md](docs/customer-agreement.md).
- **Change Date** — on 2030-05-07 this software automatically converts to **Apache License 2.0** (full open source).

> **Note on license terminology:** BUSL-1.1 is a [source-available](https://en.wikipedia.org/wiki/Source-available_software)
> license. It is **NOT** an [OSI-approved Open Source](https://opensource.org/osd) license. You may read, fork, and
> evaluate the source freely; production use requires a Commercial License from Automatia BCN until the Change Date
> (2030-05-07), after which the software automatically converts to Apache License 2.0 (full Open Source).
>
> **GitHub "Other" / NOASSERTION:** GitHub displays this repository's license as "Other" rather than "BUSL-1.1".
> This is a known upstream gap in the [Licensee Ruby gem](https://github.com/licensee/licensee) that GitHub uses
> for license detection: BUSL-1.1 is not in Licensee's `vendor/choosealicense.com/_licenses` template directory,
> so GitHub Linguist can't auto-classify the LICENSE body even though it is the canonical MariaDB BUSL-1.1 text.
> The [License Detection workflow](.github/workflows/license-check.yml) verifies the BUSL-1.1 canonical markers
> on every push to `main` to catch drift.

Related legal documents:

- [LICENSE](LICENSE) — full BUSL-1.1 text
- [NOTICE.md](NOTICE.md) — canonical attribution + trademark statement
- [docs/legal/TRADEMARKS.md](docs/legal/TRADEMARKS.md) — trademark policy (FOSSmarks-style)
- [docs/legal/PRIVACY_PHONE_HOME.md](docs/legal/PRIVACY_PHONE_HOME.md) — license heartbeat disclosure
- [docs/legal/THIRD_PARTY_LICENSES.md](docs/legal/THIRD_PARTY_LICENSES.md) — third-party dependency inventory

Contact: support@automatiabcn.com.

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

Sister products from the same team: [Automatia MCP Suite](https://automatiabcn.com/products)
(LeadPipe, InvoiceFlow, ShopOps, AdOps) · AutoPilot Business · custom AI/automation
consulting.
