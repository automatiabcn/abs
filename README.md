# ABS Studio — server

> Part of the [Automatia BCN](https://automatiabcn.com) product family · Made in Barcelona

[![License: BUSL-1.1](https://img.shields.io/badge/License-BUSL--1.1-orange.svg)](LICENSE)
[![CI](https://github.com/automatiabcn/abs/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/automatiabcn/abs/actions/workflows/ci.yml)
[![CodeQL](https://github.com/automatiabcn/abs/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/automatiabcn/abs/actions/workflows/codeql.yml)
[![Tests](https://img.shields.io/badge/tests-3668%20passing-brightgreen.svg)](#testing)
[![Lighthouse](https://img.shields.io/badge/lighthouse-%E2%89%A590%20enforced-brightgreen.svg)](docs/performance.md)
[![Tools](https://img.shields.io/badge/MCP%20tools-157-blue.svg)](docs/api-reference.md)
[![Made in Barcelona](https://img.shields.io/badge/Made%20in-Barcelona%20%F0%9F%87%AA%F0%9F%87%B8-blue.svg)](https://automatiabcn.com)

> **Automate the chaos — on your own server.** This is the server half of ABS
> Studio: the editor runs on your machine, this runs on your VPS, and nothing in
> between belongs to us. It brings the providers, the retrieval, the tools and the
> billing. **$5 a month**, seven-day trial, no card.
>
> Looking for the editor? [app.automatiabcn.com](https://app.automatiabcn.com/studio).

🇬🇧 **English (default)** · 🇹🇷 [Türkçe](README.tr.md) · 🇪🇸 [Español](README.es.md)

---

## Why a server at all

An AI editor that keeps everything on the laptop cannot search your documents,
cannot remember last week's meeting, and stops the moment one provider has a bad
afternoon. An editor that sends everything to a vendor solves those, and hands
the vendor your code.

This is the third answer: the editor talks to a server you own.

- Routes calls across **6 providers** (Anthropic + Groq + Cerebras + Gemini +
  Cloudflare + Cohere) with a circuit breaker, so one outage is not your outage.
- Ships **157 MCP tools** (RAG hybrid retrieval, judge persona ML, fullstack
  developer mode, Türkçe quality pipeline).
- Runs entirely on **your machine**. Nothing reaches an Automatia server —
  the only calls that leave are the ones you make to a provider, with your key.
- Carries the commercial parts too: licence JWT (RS256), Stripe checkout,
  customer portal, refunds.

## Features at a glance

- ⚡ **6-provider cascade** with circuit breaker + cost dashboard.
- 🛠️ **157 MCP tools**: code review, test generation, RAG hybrid, judge ML, fullstack mode, billing.
- 🌍 **i18n out of the box** — English default, Türkçe + Español alternatives (24 email templates × 3 languages).
- 🔐 **sops + age vault** — Stripe / Anthropic / SMTP secrets stay encrypted at rest.
- 💳 **Stripe-ready** — checkout, webhook (idempotent), refund, customer portal.
- 📊 **Status page + Discord alerts** — public `/v1/status` JSON + auto-refresh HTML.
- 🚀 **Docker Compose deploy** — 15-minute installation on any Linux VPS.

## Quick install (15 minutes)

```bash
# Get a Linux VPS (Hetzner CX22 = $5/month works fine) and install Docker.
ssh root@your-server-ip
curl -fsSLO https://app.automatiabcn.com/download   # the server archive
tar -xzf abs-server-*.tar.gz && cd abs-server-*
./install.sh                                        # writes .env, then run it again
```

The first run writes a `.env` for you to fill in — your domain and an admin
address — and the second pulls the published images and starts everything behind
Caddy, which obtains its own certificate. Nothing is built from source and the
first seven days need no licence key.

Detailed setup: [docs/setup-guide.md](docs/setup-guide.md).

## Pricing

| Plan | Price | Includes |
|---|---|---|
| **ABS Studio** | $5 / month | The editor and the server, every feature |

**Seven-day trial — no card, no licence key. Cancel any month. 14-day
no-questions refund on a first payment.** Buy at [app.automatiabcn.com](https://app.automatiabcn.com/).

## How it works

1. **Install** the server on your VPS with the archive above.
2. **Point** ABS Studio at it — the editor asks for the address on first launch.
3. **Activate** the licence you received by email, once the trial ends.
4. **Use** the tools from the editor, or from any MCP client you already have.

The server speaks the **Model Context Protocol** natively, so it is not limited to
our editor: anything that speaks MCP can call these tools. There is no proxy and no
man-in-the-middle — prompts go from your machine to your server to the provider you
chose, and stay there.

## Tech stack

- **Backend** — Python 3.13, FastAPI, SQLite + SQLModel, JWT RS256.
- **Frontend** — Next.js 15 (App Router), React 19, Tailwind 3.
- **MCP** — `mcp.server.fastmcp` (Anthropic-maintained Python SDK).
- **Vault** — Mozilla sops + age (4096-bit RSA optional).
- **Deploy** — Docker Compose + Caddy.
- **Tests** — pytest (3668) + vitest (275) + Playwright + Lighthouse (CI gate: performance ≥90).

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
- **Status** — write to info@automatiabcn.com. (A status page is not published yet; the host that used to be linked here never existed.)

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
