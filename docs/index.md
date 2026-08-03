# Automatia ABS Documentation

Self-host AI orchestration for Claude Code — 100+ MCP tools, a 6-provider chain, hybrid RAG and a Turkish quality pipeline, all on your own server.

---

## Quick start

| Goal | Page | Time |
|---|---|---|
| **Install** — 15-minute install with Docker Compose | [Setup Guide](setup-guide.md) | 15 min |
| **Architecture** — components, flows, license model | [Architecture](architecture.md) | 8 min |
| **MCP Tool Reference** — the full list of 100+ tools | [API Reference](api-reference.md) | reference |
| **Operations** — Stripe billing, refunds, disputes | [Billing Runbook](billing-runbook.md) | 12 min |
| **Troubleshooting** — common errors | [Troubleshooting](troubleshooting.md) | reference |
| **FAQ** — short answers | [FAQ](faq.md) | 5 min |

---

## Highlights

- **6-provider chain** — Anthropic + Groq + Cerebras + Gemini + Cloudflare + Cohere, with automatic failover and a circuit breaker.
- **104 MCP tools** — code review, test generation, hybrid RAG, judge persona ML, fullstack mode and more.
- **Sops/age vault** — your Stripe, Anthropic and SMTP secrets are always encrypted on disk.
- **Idempotent webhooks** — safe against Stripe replays and retries (017).
- **Customer Portal** — customer self-service (017).
- **Onboarding email series** — 5-stage automatic nurturing (019).
- **Token tracking + cost dashboard** — real tokens_in/out aggregation (016).

---

## License model

| Plan | Price | Term |
|---|:-:|---|
| **Solo** | $29 / month | One person, one server |
| **Team** | $19 / seat / month | From 3 seats, one server |

Every install starts with a seven-day trial — no card, no licence key. Cancel
any month. 14-day no-questions-asked refund on a first payment. GDPR compliant. Self-service through the Stripe Customer Portal.

---

## Community and support

- **Email** — `info@automatiabcn.com` (48h response while a subscription is active)
- **GitHub** — [github.com/automatiabcn/abs](https://github.com/automatiabcn/abs) (Apache 2.0 core)
- **Discord beta** — `discord.gg/abs-beta` (beta testers only)

---

## Version

Current: **v0.1.0** (2026-04-27). For the full change history see the [CHANGELOG](CHANGELOG.md).
