# Karara Varılmış Tasarım Kararları

_Son güncelleme: 2026-04-23 (ikinci oturum — 12 madde kilit)_

## STRATEJİK KARARLAR (2026-04-23)

### 1. Hedef Müşteri: **Individual Self-Host** (10-50 kişilik firma)

**Revizyon:** ~~Merkezi multi-tenant sunucu~~ → **Her kullanıcı kendi kurulumunu yapar.** Firma = 10 ayrı lisans (toplu indirim opsiyonel).

**Neden:** Teknik sadeleşme (multi-tenant DB, auth, RBAC gerekmez), MVP süresi 6 hafta → 2-3 hafta.

### 2. Marka: **Automatia ABS**

- Domain: `abs.automatiabcn.com` (subdomain, pazarlama + teknik bağımsızlık)
- Ana site: `automatiabcn.com` → "Ürünlerimiz" → ABS linki
- Logo: mevcut Automatia logosu

### 3. Operasyon: **Solo + ABS Sistemi = İşlevsel Ekip**

Pazarlama: "Biz + sistemle bir ekip gibiyiz. Dogfooding prensibi — bu ürünü kullanan ilk örnek biziz."

### 4. API Key Modeli: **Müşteri Kendi Keyleri**

Anthropic + 5 free provider (Groq, Cerebras, CloudFlare, Gemini, Cohere). Web setup wizard, `age`/`sops` ile encrypted at rest, panel'de rotation.

**Onboarding sıralaması:**
- Zorunlu: Anthropic API key
- Önerilen: Groq + Gemini (free)
- Opsiyonel: Cerebras + CloudFlare + Cohere

### 5. Feature Parity: **Tam Set + Fazlası**

SERVER'daki HER şey (75 MCP tool + 5 hook + 13 pipeline + RAG + judge + workflow + panel) + yeni eklentiler (multi-user auth opsiyonel, audit log).

### 6. MVP: **Aksiyon-Odaklı, Bana Sorarak İlerle**

Ön plan yok. Her konu başlığı için: (1) seçenekler sun (2) tradeoff (3) kullanıcı karar (4) tam yapı (5) rapor.

### 7. İki Paralel Track

- **SERVER** (Automatia BCN üretim) — dokunulmuyor
- **abs-server-product** (ürün) — temiz-oda
- Oturum başlarken hangi track belirtilir

### 8. Revenue: **One-time $299 + Opsiyonel Maintenance**

- **$299 one-time** = lifetime lisans + 1 yıl update
- **$49/yıl** opsiyonel maintenance (update + destek devam)
- Kesilince: eski sürüm sonsuza çalışır, yeni feature yok
- **Subscription YOK** (kullanıcı tercihi)

### 9. Dağıtım Modeli: **Aşamalı Dual Distribution**

- **Faz 1 (Ay 1-3):** Self-Host lifetime satış öncelik
- **Faz 2 (Ay 3-6):** Managed Cloud beta $79/ay (3-5 müşteri)
- **Faz 3 (Ay 6+):** Managed Cloud tam açılış

### 10. Team Pack

- 5 seat: $299 × 5 × 0.8 = **$1196** (%20 indirim)
- 10 seat: $299 × 10 × 0.7 = **$2093** (%30 indirim)
- 25+ seat: custom quote

### 11. Free Tier: **Yok**

- 14 gün demo mode (full feature)
- Demo biterse sistem durur
- Yabancı firma: özel beta (ücretsiz)

### 12. Ödeme: **Stripe Checkout (automatiabcn.com hesabına bağlı)**

- Lemon Squeezy yerine direkt Stripe (MoR gerekmez, Automatia entity var)
- Webhook → lisans key generator (JWT-imzalı, self-implement MVP)

---

## ARAŞTIRMALARA GÖRE TEKNİK KARARLAR (2026-04-23)

### 13. Minimum Sistem Gereksinimleri

- **2 vCPU / 4GB RAM / 20GB SSD disk**
- GPU opsiyonel (yerel Ollama fallback için)
- Ubuntu 22.04+ / Debian 12+ / Docker uyumlu herhangi Linux

### 14. SSL + Domain (seçilebilir, zorunlu değil)

**Setup wizard müşteriye iki seçenek sunar:**
- **A) IP + port** — LAN içi, domain yok, HTTP (hızlı başlangıç)
- **B) Kendi domain + HTTPS** — profesyonel, Caddy otomatik Let's Encrypt
  - Müşteri DNS'de A kaydı ekler (örn. `abs.mycompany.com` → sunucu IP)
  - Kurulumda `DOMAIN=abs.mycompany.com` verir
  - Caddy 60 saniyede SSL hazırlar

### 15. Demo Mode

- 14 gün full feature
- Panel'de geri sayım banner
- Süre bitince: "Lisans süresi doldu, satın al" ekran — sistem çalışmaz

### 16. Maintenance Bitince Davranış

- Son indirilen sürüm sonsuza çalışır
- Yeni güncelleme kilitli ("Maintenance expired, renew for $49/year")
- Yeni provider ekleme (örn. Groq v2) çalışmaz çünkü config güncellemesi gelmez

### 17. Provider Down UI

- Panel'de **banner** (yeşil = OK, sarı = degraded, kırmızı = down)
- Cascade otomatik fallback (sessiz)
- Admin bildirimi: "Groq 15 dakikadır hata veriyor, fallback Cerebras"

### 18. RAG Indexing UX

- Panel'de **"Projects"** sayfası
- "Add Project" → path gir → otomatik index başlar
- Progress bar + log (sembol count, file count)
- Git hook opsiyonel (auto-reindex on commit)

### 19. Update Mekanizması

- `docker-compose pull && docker-compose up -d`
- Panel'de "Update available v1.x.y" notification
- Tek tık otomatik update button (opsiyonel)
- Breaking changes için manuel migration script

### 20. Refund Policy

- **14 gün no-questions-asked** iade
- Stripe tek tık refund
- Sonrasında: case-by-case (rare)

### 21. Privacy Policy (Müşteriye Transparent)

Kritik ifade:
> "ABS, müşteri promptlarını ve kod parçalarını doğrudan Anthropic'e ve seçilen diğer LLM provider'lara iletir. Bu, Claude API kullanımının doğal bir parçasıdır. ABS sunucumuza kod veya prompt verisi GELMEZ — sadece lisans doğrulama sinyali alır. Müşteri, kendi Anthropic / Groq / Gemini vb. hesaplarının Terms of Service'ine tabidir."

---

## OPERASYON KARARLARI (2026-04-23)

### 22. ABS Central Watchdog — Bizim Sunucumuzda

- `abs.automatiabcn.com/watchdog/` altında Python cron servis
- Günlük 06:00 scan: provider pricing + changelog + status JSON + community
- Değişiklik → Discord/email alert → bizim release hazırlığı
- Hetzner $5-10/ay VPS yeterli

### 23. Provider Config Update Channel

- Bizim repo: `infra/provider-configs/` klasörü
- Her release'de `*.yaml` dosyaları güncellenebilir
- Müşteri update alınca yeni config geçerli
- Kritik değişiklik (provider deprecated) → hotfix release + müşteri email

### 24. 7-Katmanlı Koruma Mimarisi

1. **Abstraction layer** (model aliases, `fast-reasoning` gibi isimler)
2. **Circuit breaker** (5 hata → open, 60s sonra half-open)
3. **Cascade fallback** (Groq → Cerebras → CF → Gemini → Anthropic)
4. **Semantic cache** (5dk TTL, provider yavaş/down'da cache'ten dön)
5. **Health monitor** (müşteri sunucusunda, 60s provider ping)
6. **Central Watchdog** (bizim tarafta, günlük changelog scan)
7. **Update channel** (release-based config güncelleme)

Detay: `docs/operations.md`

---

## ATLANAN / ERTELENMIŞ (şu an değil)

- **Anthropic TOS derinlemesine legal review** — önemli ama şu an blocker değil (API key commercial terms = legal OK)
- **Encryption AES-256 profile paketi** — E13.5 roadmap'te
- **SOC 2 / ISO 27001** — 100+ müşteri sonrası
- **Multi-language** (sadece TR/EN yeterli)
- **Affiliate/referral program** — MVP sonrası
- **DPA template** — Enterprise talep edince
- **Public Kubernetes helm chart** — ileride
