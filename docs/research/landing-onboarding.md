# Automatia ABS — Landing ve Onboarding Stratejisi

Bu belge, `abs.automatiabcn.com` landing sayfasının yapısını ve kullanıcı onboarding akışını detaylandırır.

## Landing Sayfası Yapısı

| Bölüm | Amaç |
|---|---|
| Hero | Değer önermesi + hızlı anlatım + CTA |
| Features | Sayısal, spesifik yetenekler |
| Pricing | 3 katman (self-host + maintenance + cloud faz 3+) |
| Docs link | Detay için yönlendirme |
| Community | Automatia kanalları |
| Demo video | 60-90 saniye görsel tur |
| Social proof | Dogfooding + ileride testimonial |
| FAQ | Sık dönüşüm engelleri (legal, kurulum, TOS) |

## Hero Varyantları

### Varyant 1 — Maliyet + Verim
> **Başlık:** Claude Pro $20 aboneliğinizle Max 20x seviyesinde çalışın — Automatia ABS ile kendi sunucunuzda.
>
> **Alt metin:** 75 MCP tool + 6 sağlayıcı cascade (Anthropic + 5 ücretsiz) + Türkçe kalite pipeline'ı. Kurulum 15 dakika. 14 gün demo, 14 gün iade.
>
> **CTA:** 14 Günlük Demoyu İndir

### Varyant 2 — Kontrol + Şeffaflık
> **Başlık:** Kendi sunucunuzda, kendi API keyleriniz ile, tam kontrol.
>
> **Alt metin:** Automatia ABS kodu sizden çıkmaz. Provider'a doğrudan müşteri olur, verileriniz bizim sunucuya gelmez. Tek seferlik $299.
>
> **CTA:** Kurulum Rehberi

### Varyant 3 — Geliştirici Odaklı
> **Başlık:** Claude Code'u genişletin, değiştirmeyin. 75 MCP tool tek paket.
>
> **Alt metin:** Terminal'den `claude` açarsınız, ABS arkada cascade + quality pipeline + RAG + judge yapar. Siz farketmezsiniz, çıktı daha iyi olur.
>
> **CTA:** Nasıl Çalışır

## Features Bölümü — Sayısal Değer Önermesi

Generic marketing yerine **ham sayılar ve gerçek karşılaştırmalar**:

- **75 MCP tool** — hazır kurulu, uzatılabilir
- **13 quality pipeline** — qual-code, qual-tr, qual-analysis, qual-translate + varyantlar
- **6 provider cascade** — Anthropic + Groq (14K req/gün) + Cerebras (1M token/gün) + Gemini + CloudFlare + Cohere
- **Symbol-aware RAG** — 10.000+ sembol, callsite graph
- **Senior Judge** — her patch'e AST + LLM skoru (0-10)
- **Workflow durability** — SQLite checkpoint, pipeline resume
- **Kurulum 15 dakika** — `docker-compose up` + setup wizard
- **Dogfooding credibility** — kurucu 6 aydır bizzat kullanıyor

## Pricing Sayfası

3 ana kart, şeffaf:

### Self-Host Lifetime — $299 one-time
- Tek seferlik ödeme
- Ömür boyu kullanım
- 1 yıl update dahil
- 1 lisans key → 1 kurulum
- Email destek (14 gün response)

### Self-Host + Maintenance — $299 + $49/yıl
- Yukarıdaki her şey +
- Sürekli update (yeni provider, yeni MCP tool)
- Security patch öncelikli
- Email destek (48 saat)
- Her yıl yenilenir, iptal edilebilir

### Managed Cloud — $79/ay (Faz 3+, yakında)
- Kurulum yok, Automatia sunucusunda hostlarız
- Otomatik update
- Backup + monitoring 7/24
- Support öncelikli
- Cancel anytime

### Team Pack (her katmanda geçerli)
- 5 seat: %20 indirim
- 10 seat: %30 indirim
- 25+ seat: custom quote

## Setup Wizard — 6 Adım

Müşteri `docker-compose up` sonrası tarayıcıda panel açılır:

1. **Admin Account** — email + parola (lisans key'le bağlı)
2. **Lisans Key** — satın alma email'inden gelen JWT key yapıştırılır, validate edilir
3. **Domain/Erişim** — iki seçenek:
   - IP + port (LAN, HTTP)
   - Kendi domain + otomatik Let's Encrypt HTTPS
4. **Anthropic API Key (zorunlu)** — Console linki + "Nasıl alırım" video + test ping
5. **Opsiyonel Providers** — Groq, Gemini, Cerebras, CloudFlare, Cohere (her biri "Skip" edilebilir)
6. **Bitir** — ilk test prompt tetiklenir, başarılıysa yeşil tik, panel açılır

## İlk 5 Dakika Deneyimi

```
0:00 — Müşteri landing'e geldi, "Demo İndir" bastı, Docker compose dosyası + install.sh email'e geldi
0:30 — Sunucuda: `docker-compose up -d`
2:00 — Browser: http://sunucu-ip:8443 → setup wizard
3:00 — Adım 1-4 tamam (admin account + lisans + Anthropic key)
4:00 — Adım 5 skip edildi → Bitir
4:30 — Ana panel açıldı, "İlk prompt'u test et" banner
5:00 — Terminal'de `claude mcp add abs http://sunucu-ip:8443/mcp` → `claude` açıldı → prompt girildi → ABS orkestre etti → sonuç geldi
```

## Social Proof (aşamalı)

### MVP aşaması (Ay 1)
- "Automatia kurucusu ABS'yi kendi üretim sisteminde 6 aydır kullanıyor"
- GitHub repo (private ama müşteriye erişilebilir)
- Dogfood screenshot galerisi

### Büyüme aşaması (Ay 2-6)
- İlk müşteri testimonial (yabancı firma, NDA'dan sonra)
- Case study: "X firması ABS ile aylık $1200 tasarruf"
- Müşteri logoları (izin alınarak)

## Demo Video Planı

**Süre:** 60-90 saniye

**Script:**
- 0-10s: Problem — "Claude Pro $20, ama ekipte herkes Max plana geçmek istiyor, $1000/ay"
- 10-30s: Çözüm — `docker-compose up`, setup wizard, ilk prompt
- 30-50s: Panel demo — cosmos widget, provider cascade canlı, quality pipeline
- 50-80s: Değer — "Ekibiniz $299'a ömür boyu, kendi sunucunuzda, tam kontrol"
- 80-90s: CTA — "abs.automatiabcn.com/demo"

**Platform:** Loom (hosted) veya YouTube embed. Hero bölümde autoplay (muted).

## Dönüşüm Engelleri ve Çözümler

| Engel | Çözüm |
|---|---|
| "Anthropic TOS ihlali mi?" | FAQ: "API key commercial terms (pay-per-use), OAuth token değil, legal %100" |
| "Kurulum çok teknik" | Demo video + Docker Compose tek dosya |
| "Lisans kayboluyorsa?" | Email + panel'de key saklı, recover edilebilir |
| "Refund var mı?" | 14 gün no-questions-asked Stripe refund |
| "Destek nerede?" | Automatia email + Discord (Faz 2+) |
| "Benim için fayda sağlar mı?" | Demo 14 gün, risk yok |

## Tech Stack Kararı

### Landing Page
- **Next.js** önerim (automatiabcn.com ile uyum, Vercel deploy)
- Alternative: Astro (statik, SEO güçlü)
- Tailwind CSS + shadcn/ui

### Docs Platform
- **Mintlify** önerim — API doc automation, modern UI
- Alternative: Docusaurus (daha geniş community)

### Demo Environment
- Play.abs.automatiabcn.com (opsiyonel) — sandbox demo, deneme için
- Alternatif: Docker Compose ile local demo

## Next Steps

Landing implementation sırasında terminal 2 için prompt `_agent-tasks/003-landing.md` altında yazılacak. İçerik:
- Next.js project scaffold
- 5-6 sayfa component yapısı (hero, features, pricing, FAQ, docs-link)
- Tailwind + shadcn setup
- Stripe Checkout integration (frontend)
- Vercel deploy

---

**Son güncelleme:** 2026-04-23
**Domain status:** abs.automatiabcn.com (subdomain, DNS setup pending)
