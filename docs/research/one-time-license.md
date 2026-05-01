# ABS Tek Seferlik Lisans Modeli

Bu belge, ABS'nin revenue model kararını ve teknik lisans mekaniğini detaylandırır.

## ABS Lisans Modeli Özeti

ABS **one-time lifetime license + opsiyonel maintenance** modelini benimser:

- **$299 tek seferlik** — ömür boyu kullanım + 1 yıl update dahil
- **$49/yıl opsiyonel maintenance** — update + destek devam
- Maintenance kesilince: son indirilen sürüm sonsuza çalışır, yeni feature kilitli

## Neden Subscription Yerine One-Time?

Kullanıcı tercihi + stratejik nedenler:
- **Kullanıcı kontrolü:** Kullanıcı yazılıma sahip, abonelik zorunluluğu yok
- **Maliyet öngörülebilirlik:** Başlangıç + opsiyonel yıllık maintenance, şeffaf
- **Sahiplik hissi:** Alıcı ürüne sahip olduğunu hisseder
- **Basitlik:** İptal/yeniden etkinleştirme karmaşası yok
- **Automatia marka:** Mevcut Stripe hesabı + kurumsal yapı uyumlu

## Lisans Key Mekaniği

### JWT-İmzalı Anahtar (MVP implementation)

- Her anahtar **JWT** (JSON Web Token) formatında, RS256 ile imzalanır
- Payload: `{customer_id, purchase_date, tier, expiry_date, max_seats}`
- Müşteri makinesinde **public key** ile doğrulama (private key bizim sunucuda)
- **Offline activation:** key doğrulama phone-home gerektirmez, JWT imza yeter
- **Revocation:** JWT içinde 30-gün TTL, re-activation bizim servisten (blokluysa fail)

MVP effort: 2-3 gün (Stripe webhook → Python JWT üretici → email)

### Stripe Webhook Akışı

```
1. Müşteri abs.automatiabcn.com/pricing → "Buy Now"
2. Stripe Checkout ($299)
3. Ödeme başarılı → checkout.session.completed webhook
4. Bizim endpoint: webhook signature doğrula
5. License generator: JWT imzala (customer_id + tier)
6. Email müşteriye: "İşte lisans key'in + kurulum linki"
7. Müşteri panel'e key girer → sistem aktifleşir
```

### Güncelleme Politikası

- İlk 1 yıl: tüm update dahil
- 1 yıl sonra: $49/yıl maintenance plan opsiyonel
  - Alırsa: yeni feature + patch + provider config updates
  - Almazsa: son indirilen sürüm sonsuza çalışır (yeni provider eklenince bozulabilir)
- Security patches: **her zaman ücretsiz**, maintenance'tan bağımsız

### Maintenance Bitince

- Panel'de uyarı: "Maintenance süresi doldu, renew $49/year"
- Eski sürüm çalışır
- Yeni provider_configs gelmez → eklenen yeni sağlayıcılar mevcut değil
- Yeni MCP tool'lar gelmez
- Kullanıcı tekrar alırsa: son 1 yıl atlanır, güncel sürüme geçer

## Refund Policy

- **14 gün no-questions-asked iade**
- Stripe tek tık refund
- Sonrasında: özel durum (edge case)

## Team Pack

| Seat sayısı | İndirim | Total |
|---|---|---|
| 1 seat | - | $299 |
| 5 seat | %20 | $1.196 |
| 10 seat | %30 | $2.093 |
| 25+ seat | Custom | Sales-assist |

**Team pack mekaniği:** Tek master key + seat count; her kurulum aynı key'i kullanır, but limit seat'a göre.

## Rakip Lisans Karşılaştırma

| Ürün | Model | Fiyat | Güncelleme |
|---|---|---|---|
| **Sketch** (eski) | Lifetime + 1yr update | $99 Mac | Sonra subscription'a geçti |
| **JetBrains** | Subscription + perpetual fallback | Sub | 12 ay abonelik → perpetual key |
| **Plex Pass** | Lifetime | $249.99 (2025 artış) | Ömür boyu |
| **Sublime Text** | Lifetime + 3yr update | $99 | Yenileme opsiyonel |
| **Affinity** | Lifetime | $165 | Canva 2026 free yaptı |
| **Automatia ABS** | Lifetime + 1yr + opt maintenance | **$299** | Benzer Sublime patterni |

## Alternatif Araçlar (ileride değerlendirme)

MVP sonrası büyümede:

- **Keygen.sh** ($49/ay) — Hazır lisans API, daha rich feature
- **LicenseSpring** — Enterprise-grade, offline activation güçlü
- **Paddle / Lemon Squeezy** — Merchant of Record (global tax otomatik) — ama Automatia zaten Stripe, geçişe gerek yok

## Implementasyon Referansı

Detay implementation `_agent-tasks/002-licensing.md` altında yazılacak. İçerik:
- Stripe webhook endpoint (Python, FastAPI)
- JWT generator (cryptography library)
- Email template (customer receipt + key + install link)
- Panel'de key input + validate + activate flow
- Admin dashboard'da müşteri + key yönetimi (bizim tarafta)

---

**Son güncelleme:** 2026-04-23
**Stripe status:** Automatiabcn.com hesabı bağlı ✓
