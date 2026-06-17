# Automatia ABS Documentation

Self-host AI orchestration for Claude Code — kendi sunucunda 100+ MCP tool, 6 sağlayıcı cascade, RAG hybrid ve Türkçe kalite pipeline.

---

## Hızlı başlangıç

| Hedef | Sayfa | Süre |
|---|---|---|
| **Kurulum** — Docker Compose ile 15dk install | [Setup Guide](setup-guide.md) | 15 dk |
| **Mimari** — Bileşenler, akışlar, lisans modeli | [Architecture](architecture.md) | 8 dk |
| **MCP Tool Reference** — 100+ aracın tam listesi | [API Reference](api-reference.md) | tarafından |
| **Operasyon** — Stripe billing, refund, dispute | [Billing Runbook](billing-runbook.md) | 12 dk |
| **Sorun Giderme** — Yaygın hatalar | [Troubleshooting](troubleshooting.md) | tarafından |
| **SSS** — Kısa cevaplar | [FAQ](faq.md) | 5 dk |

---

## Öne çıkan özellikler

- **6 sağlayıcı cascade** — Anthropic + Groq + Cerebras + Gemini + Cloudflare + Cohere otomatik failover, circuit breaker.
- **104 MCP tool** — Code review, test üretimi, RAG hybrid, judge persona ML, fullstack mode, vb.
- **Sops/age vault** — Stripe + Anthropic + SMTP secret'lar disk üzerinde her zaman şifreli.
- **Idempotent webhook** — Stripe replay/retry safe (017).
- **Customer Portal** — Müşteri self-service (017).
- **Onboarding email serisi** — 5-aşamalı otomatik nurturing (019).
- **Token tracking + cost dashboard** — Gerçek tokens_in/out aggregation (016).

---

## Lisans modeli

| Plan | Fiyat | Süre |
|---|:-:|---|
| **Self-Host Lifetime** | $299 tek seferlik | Ömür boyu kullanım + 1 yıl güncelleme |
| **+ Maintenance** | +$49/yıl | Sürekli güncelleme + öncelikli destek |
| **Team Pack 5** | $1196 | 5 seat, %20 indirim |
| **Team Pack 10** | $2093 | 10 seat, %30 indirim |

14 gün koşulsuz iade. GDPR uyumlu. Stripe Customer Portal self-service.

---

## Topluluk + destek

- **Email** — `support@automatiabcn.com` (48s yanıt, Maintenance: 24s)
- **GitHub** — [github.com/automatiabcn/abs](https://github.com/automatiabcn/abs) (Apache 2.0 core)
- **Discord beta** — `discord.gg/abs-beta` (yalnızca beta tester)
- **Status** — `status.abs.automatiabcn.com` (Cloudflare uptime monitor)

---

## Sürüm

Şu an: **v0.1.0** (2026-04-27). Tam değişiklik kayıtları için [CHANGELOG](CHANGELOG.md).
