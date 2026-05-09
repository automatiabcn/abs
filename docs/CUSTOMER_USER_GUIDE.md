# Automatia ABS — Customer User Guide

> **Self-hosted AI orchestrator. Automate the chaos on your own server.**
>
> Version: 1.0 · Last updated: 2026-05-09 · License: BSL 1.1

---

## İçindekiler / Contents

1. [Hoş geldiniz](#hoşgeldiniz)
2. [Satın alma akışı](#1-satın-alma-akışı)
3. [VPS hazırlama](#2-vps-hazırlama)
4. [ABS kurulumu](#3-abs-kurulumu)
5. [İlk yapılandırma (Setup Wizard)](#4-i̇lk-yapılandırma-setup-wizard)
6. [Sağlayıcı API anahtarları](#5-sağlayıcı-api-anahtarları)
7. [İlk sohbet](#6-i̇lk-sohbet)
8. [RAG bilgi tabanı](#7-rag-bilgi-tabanı)
9. [Quality Pipelines](#8-quality-pipelines)
10. [Workflow Builder](#9-workflow-builder)
11. [Knowledge Graph](#10-knowledge-graph)
12. [Plugin Marketplace](#11-plugin-marketplace)
13. [Yönetim ayarları](#12-yönetim-ayarları)
14. [Lisans & iade](#13-lisans--i̇ade)
15. [Sorun giderme](#14-sorun-giderme)
16. [Yasal uyarılar & marka bildirimi](#yasal-uyarılar--marka-bildirimi)

---

## Hoş geldiniz

ABS (Automation Backbone System), kendi sunucunuzda çalışan bir AI orkestratördür. 100+ MCP tool, 6 sağlayıcılı cascade router (Anthropic, Groq, Cerebras, Gemini, Cloudflare, Cohere) ve hibrit RAG ile kurumsal AI altyapısı sunar.

**Kullanım hakları:** Müşteri olarak ABS'yi kendi sunucunuzda **production** ortamında kullanma hakkına sahipsiniz. BSL 1.1 lisansı 4 yıl sonra (2030-05-07) Apache 2.0'a otomatik dönüşür.

**Bu rehberin kapsamı:** Satın aldıktan sonra kuruluma kadar geçen 30 dakikalık akış + temel kullanım. İleri seviye konular için [docs/api-reference.md](api-reference.md) ve [docs/runbooks/](runbooks/).

---

## 1. Satın alma akışı

### 1.1 Ürün sayfası

[automatiabcn.com/products/abs](https://automatiabcn.com/products/abs) — 3 tier seçeneği:

| Tier | Fiyat | Kapsam |
|------|-------|--------|
| Self-Host | $299 (tek seferlik) | 1 seat · 1 deployment · email destek (48h) |
| Team 5 | $1,196/yıl | 5 seat · priority email (24h) · onboarding call |
| Team 10 | $2,093/yıl | 10 seat · 24h SLA · founder hotline |

> Her tier 14 gün koşulsuz iade garantilidir. İade için bkz. [Bölüm 13](#13-lisans--i̇ade).

**Ekran**: `faz_c_phase1_1_landing_en.png` — Hero, özellikler, fiyatlandırma kartları, FAQ.

### 1.2 Ödeme

"Buy now" butonu sizi güvenli ödeme sayfasına yönlendirir (3D Secure desteklenir). Bilgi formu:

- E-posta (lisans bu adrese gönderilir — doğru girin)
- Kart numarası, son kullanma, CVC
- Kart sahibi adı + ülke

**Ekran**: `faz_c_phase1_2_stripe_filled.png` — Çoklu ödeme yöntemi (kart, Link, Amazon Pay) + güvenli sandbox işlem.

### 1.3 Onay

Ödeme onaylandıktan sonra "Thanks for your payment" sayfası görünür ve:

1. **Welcome email** (sipariş + kurulum 7 adımı) ~1 dakika içinde geldiği e-postaya iletilir.
2. **Founder bildirimi** Automatia BCN ekibine düşer.
3. **Lisans JWT** founder tarafından mint edilip ayrı bir e-postayla 24 saat içinde gönderilir.

**Ekran**: `faz_c_phase1_2b_stripe_paid.png` — Ödeme tamamlandı bildirimi.

> **Email ulaşmadı mı?** Spam klasörünü kontrol edin. Hâlâ yoksa `info@automatiabcn.com` adresine sipariş ID'nizle yazın.

---

## 2. VPS hazırlama

ABS herhangi bir Linux x86_64 / ARM64 sunucusunda çalışır. **Minimum gereksinim:** 2 vCPU, 4 GB RAM, 40 GB SSD, Ubuntu 22.04 LTS önerilir.

### 2.1 Önerilen sağlayıcılar

| Sağlayıcı | Plan | Aylık | Bölge |
|-----------|------|-------|-------|
| Hetzner Cloud | CPX22 (AMD, 2vCPU, 4GB, 80GB NVMe) | ≈ €4.99 | Almanya/Finlandiya/ABD |
| DigitalOcean | Basic 4GB | ≈ $24 | Frankfurt/Amsterdam/NYC |
| Linode (Akamai) | Linode 4GB | ≈ $24 | global |
| Vultr | Cloud Compute 4GB | ≈ $24 | global |
| Kendi sunucunuz | Bare-metal / Proxmox VM | — | yerel |

> Bu liste yalnızca yönlendiricidir; satışa aracılık etmiyoruz. Ürün adları ilgili şirketlerin tescilli markalarıdır.

### 2.2 Sunucu oluşturma (genel adımlar)

1. Sağlayıcının web panelinde yeni sunucu oluşturun: 2 vCPU + 4 GB RAM minimum.
2. İmaj: **Ubuntu 22.04 LTS**.
3. SSH anahtarınızı yükleyin (yoksa `ssh-keygen -t ed25519 -C "abs-customer"` ile oluşturun, public anahtarı paneline yapıştırın).
4. Sunucu oluştuğunda **public IPv4** adresini not alın.
5. SSH ile bağlanın: `ssh -i ~/.ssh/abs-customer root@<IPv4>`.

> **Domain isteğe bağlıdır.** Domain yoksa `<IPv4>.sslip.io` formatı (örn. `203-0-113-7.sslip.io`) Caddy'nin Let's Encrypt sertifikasını otomatik üretmesini sağlar. DNS kaydı eklemenize gerek kalmaz.

---

## 3. ABS kurulumu

### 3.1 Docker kurulumu

Ubuntu 22.04 üzerinde:

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2 docker-buildx
systemctl enable --now docker
docker --version          # 24+ olmalı
docker compose version    # v2.20+ olmalı
```

### 3.2 ABS deposu

```bash
git clone https://github.com/automatiabcn/abs.git /opt/abs
cd /opt/abs
```

> Repo herkese açıktır (BSL 1.1). Kaynak kod inceleyebilir, ancak ticari kullanım için lisans gerekir.

### 3.3 Ortam dosyası (.env)

```bash
cp .env.example .env
nano .env
```

Doldurulması gereken alanlar (welcome email'inde örnekleri var):

```env
ABS_LICENSE_KEY=<lisans-jwt-mailden>
ABS_PUBLIC_HOSTNAME=<domain veya 203-0-113-7.sslip.io>
ABS_PUBLIC_URL=https://${ABS_PUBLIC_HOSTNAME}
ABS_ACME_EMAIL=<sertifika-bildirim-adresiniz>
ABS_VAULT_KEY=$(openssl rand -base64 32)
ABS_VERSION=1.0.0-rc4
ANTHROPIC_API_KEY=sk-ant-...   # Bölüm 5'te alacaksınız
```

### 3.4 Stack başlatma

```bash
docker compose up -d
docker compose ps          # 4 container "healthy" durumunda olmalı (≈30 sn)
```

İlk başlangıçta arka uç GHCR'dan yaklaşık 1.3 GB indirir.

### 3.5 Sağlık kontrolü

```bash
curl -s https://${ABS_PUBLIC_HOSTNAME}/healthz
# beklenen yanıt: {"status":"ok","service":"abs-backend"}
```

> Caddy ilk açılışta ~30 sn içinde Let's Encrypt sertifikasını üretir. Tarayıcıda ilk istek bu süreyi bekleyebilir.

---

## 4. İlk yapılandırma (Setup Wizard)

Tarayıcıda `https://<ABS_PUBLIC_HOSTNAME>/setup` adresini açın. 6 adımlı sihirbaz karşılar.

**Ekran**: `faz_c_phase3_5_setup_wizard_landed.png` — Adım listesi sol nav, "Automate the Chaos" markası.

### Adım 1 — Yönetici hesabı

Panel girişi yapacak ana hesabı tanımlayın:
- E-posta (örn. `admin@şirketiniz.com`)
- Parola (en az 8 karakter)

### Adım 2 — Lisans

Mailden gelen JWT token'ını yapıştırın → "Aktive et". Backend imzayı doğrular.

### Adım 3 — Domain

Mode seçimi:
- **IP**: tek seferlik smoke test (`<IP>.sslip.io`).
- **Domain**: kendi alanınız (önerilen).

SSL modu: **ACME** (Let's Encrypt) varsayılan.

### Adım 4 — Anthropic API key

Anthropic Console'dan ([console.anthropic.com](https://console.anthropic.com/)) bir API anahtarı oluşturup yapıştırın. Anahtar `sk-ant-` ile başlamalıdır. Detaylı sağlayıcı kayıt akışı için [Bölüm 5](#5-sağlayıcı-api-anahtarları).

### Adım 5 — Diğer sağlayıcılar (opsiyonel)

Cascade router için ek sağlayıcılar:
- Groq (`gsk_...`)
- Gemini / Google AI (`AIza...`)
- Cerebras (`csk-...`)
- Cohere (`...`)
- Cloudflare Workers AI (Account ID + API Token)

Hangisini girerseniz fallback zincirine eklenir.

### Adım 6 — Test

Yapılandırılan sağlayıcılar için ping testi sonuçlarını gösterir. PASS olunca sihirbaz tamamlanır.

---

## 5. Sağlayıcı API anahtarları

ABS, sağlayıcı API'lerini **siz kendi hesabınızdan** alır ve yine **kendi hesabınızdan** ücretlendirilirsiniz. ABS aracı ücreti almaz.

### 5.1 Anthropic Claude (önerilir, primary)

1. [console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys → "Create Key"
2. İsim: `abs-orchestrator-prod`
3. Workspace: kendi varsayılanınız
4. Anahtar bir kez gösterilir — güvenli yere kaydedin (`sk-ant-api03-...`)
5. Setup Wizard Adım 4'e yapıştırın

> **Maliyet:** Claude API kullanım başına faturalanır (token bazlı). Pro plan $20/ay aboneliği API faturasını kapsar.

### 5.2 Groq (ücretsiz tier, hızlı)

1. [console.groq.com](https://console.groq.com/keys) → "Create API Key" 
2. Anahtar `gsk_` ile başlar
3. Setup Wizard Adım 5

> Ücretsiz tier yüksek hız (Llama 3.3 70B) için mükemmel. Rate limit: 30 req/dk.

### 5.3 Google Gemini (ücretsiz tier)

1. [aistudio.google.com](https://aistudio.google.com/app/apikey) → "Create API key"
2. Anahtar `AIza` ile başlar
3. Setup Wizard Adım 5

> Gemini 2.5 Flash ücretsiz limit yüksek. Pro plan opsiyonel.

### 5.4 Cerebras (ultra hızlı)

1. [cloud.cerebras.ai](https://cloud.cerebras.ai/) → API Keys
2. Anahtar `csk-` ile başlar
3. Setup Wizard Adım 5

> Cerebras WSE-3 ile saniyeler yerine milisaniyeler.

### 5.5 Cohere (ücretsiz trial)

1. [dashboard.cohere.com](https://dashboard.cohere.com/api-keys) → "API Keys"
2. Trial key başlar
3. Setup Wizard Adım 5

### 5.6 Cloudflare Workers AI

1. [dash.cloudflare.com](https://dash.cloudflare.com/) → AI → Workers AI
2. Account ID: sağ alt köşeden kopyalayın
3. API Token: My Profile → API Tokens → Workers AI Read template

> **Marka uyarısı:** Anthropic, Claude, Groq, Gemini, Cerebras, Cohere ve Cloudflare ilgili şirketlerin tescilli markalarıdır. ABS bu hizmetlerin müşteri tarafı entegrasyonunu sağlar; resmi ortaklık veya destek anlamına gelmez.

---

## 6. İlk sohbet

Panel girişi: `https://<domain>/login` → Setup Wizard'da tanımladığınız admin email/parola.

**Ekran**: `faz_c_phase4_admin_dashboard.png` — Sol nav: Sohbet, Workflow, Kullanım, MCP Tools, RAG, Quality Pipelines.

### 6.1 Sohbet başlatma

Sol navdan **Sohbet** → Yeni sohbet → mesajınızı yazın. Yanıt cascade router'dan gelir.

`meta` blokunda yanıt veren sağlayıcı (`provider: anthropic`), token sayısı ve gecikme görünür.

### 6.2 Pipeline seçimi

Standart sohbet `auto_direct` pipeline kullanır. İleri seviye pipeline'lar:

| Pipeline | Amaç | Süre |
|----------|------|------|
| `auto_direct` | Tek model hızlı yanıt | ~1-3 sn |
| `qual_code` | Kod üretimi (üret→doğrula→düzelt) | ~3-8 sn |
| `qual_tr` | Türkçe metin (üret→kontrol→cilala) | ~3-8 sn |
| `qual_translate` | Çeviri (çevir→geri-çevir→doğrula) | ~3-8 sn |
| `qual_analysis` | 3-perspektif analiz + sentez | ~10-15 sn |
| `race_code` | 3 model yarışı, en hızlı kazanır | ~2-5 sn |

Pipeline UI'da kart olarak görünür. Tıklayıp prompt yazın → Çalıştır.

**Ekran**: `faz_c_test_admin_pipelines.png`, `faz_c_test_pipelines_qual_code_run.png`.

---

## 7. RAG bilgi tabanı

Sol nav → **RAG Bilgi Tabanı**.

**Ekran**: `faz_c_phase4_rag.png` — Doküman sayısı, chunk, toplam boyut, top-K ayarı.

### 7.1 Doküman yükleme

PDF · MD · TXT · DOCX formatları (≤ 25 MB). Sürükle-bırak veya "Dosya seç". BGE-M3 dense embedding ile otomatik chunk + index.

### 7.2 Sorgu

"Sorgu test" alanına Türkçe veya İngilizce soru yazın → "Sorguyu çalıştır". Top-K (varsayılan 5) sonuç + skor.

> **Veri güvenliği:** RAG indeksi tamamen sunucunuzda (ChromaDB + Qdrant). Anthropic'e veya başka bir sağlayıcıya doküman içeriği iletilmez — yalnızca sorgu + retrieved chunks LLM'e geçer (yanıt oluşturma için).

---

## 8. Quality Pipelines

Tek model değil, zincir: ABS kalite imzası — üret → doğrula → düzelt veya yarış (en hızlı kazanır).

9 pipeline mevcut. Detay [Bölüm 6.2](#62-pipeline-seçimi).

**Ekran**: `faz_c_test_admin_pipelines.png`.

> Pipeline'lar Anthropic + diğer sağlayıcıları paralel kullanır; çıktı kalitesi tek modele göre artar, maliyet ölçülü kalır (cascade Claude düşerken Groq devreye girer).

---

## 9. Workflow Builder

Doğal dilde anlattığınız iş akışını otomatik n8n-uyumlu node grafiğine dönüştürür.

**Ekran**: `faz_c_test_admin_workflow.png` — RAG-grounded customer chat örneği: Cerbos check → RAG query → Compose answer → Return JSON.

### 9.1 Workflow oluşturma

1. "Workflow'unu anlat" alanına Türkçe açıklama yazın (örn. "Gelen Gmail mesajlarını sınıflandır ve satış etiketli e-postalara yanıt taslağı hazırla").
2. **Sentezle** → ABS LLM ile JSON workflow üretir.
3. Düzenle → HITL (insan onayı) adımı ekleyebilirsiniz.
4. **Kuru çalıştır** → simülasyon.
5. **Kaydet** → tenant workflow listesine eklenir, n8n'e export edilebilir.

> Çalıştırma başına tahmini maliyet panelde gösterilir.

---

## 10. Knowledge Graph

Neo4j 5 üzerine kurulu kurum graph'ı: Person, Org, Project, Ticket node'ları + WORKS_AT, OWNS, MANAGES, ASSIGNED_TO ilişki tipleri.

**Ekran**: `faz_c_test_admin_graph.png` — Schema, hazır sorgular, Cypher editörü, doğal dil sorgu.

### 10.1 Cypher editor

Read-only kullanıcılar yalnızca MATCH/RETURN çalıştırabilir. Örnek:

```cypher
MATCH (p:Person)-[:WORKS_AT]->(o:Org {name:"Acme"})
RETURN p.name, p.email LIMIT 25
```

### 10.2 Doğal dil sorgu

"Acme şirketinde çalışan tüm kişileri bul" → Cypher üretir → Çalıştır.

> Neo4j Bolt protokolü Inc. Cypher Neo4j Inc. tescilli markasıdır. Kullanım Neo4j Community Edition lisansına tabidir.

---

## 11. Plugin Marketplace

Sol nav → **Marketplace**. ABS ekosistemi: LLM sağlayıcıları, RAG kaynakları, MCP araçları, workflow şablonları.

**Ekran**: `faz_c_test_admin_marketplace.png` — Slack Receiver, Gmail Archiver, Linear Bridge, Notion Sync, Postgres Mirror.

### 11.1 Plugin kurma

1. Plugin kartında **Kur** → "Review permissions" modal açılır.
2. Network egress, mount'lar, secrets, kaynak kullanımı (CPU/RAM), tenant kapsamı listelenir.
3. Onay kutusunu işaretleyin → **Onayla & Kur**.
4. Plugin sandbox cgroup içinde başlatılır, audit'e düşer.

**Ekran**: `faz_c_test_marketplace_install.png` — Slack Receiver permission review.

### 11.2 Filtreleme

Üstteki kategori chip'leri (LLM Sağlayıcı / RAG Kaynağı / MCP Aracı / Workflow Şablonu) + arama kutusu.

> Slack, Gmail, Linear, Notion, Postgres ilgili şirketlerin tescilli markalarıdır. Plugin'ler bu hizmetlerin müşteri tarafı API'lerini kullanır.

---

## 12. Yönetim ayarları

Sol nav → **Ayarlar**. 7 sub-tab:

| Tab | İçerik |
|-----|--------|
| Genel | Tenant adı, slug, domain, SSL |
| Lisans | Aktif lisans durumu, JWT yenileme |
| Sağlayıcılar | Cascade sırası, mock mode, her sağlayıcı için "Yapılandır" |
| Webhook'lar | Slack, e-posta, Discord webhook URL'leri |
| Uyarılar | Quota uyarı eşiği, latency p95 SLO |
| Marka | Logo, favicon, brand renk, login mesajı |
| Güvenlik | Magic-link ömrü, oturum süresi, audience kontrolü |

**Ekran**: `faz_c_test_admin_settings.png`, `faz_c_test_settings_after_rc3.png`, `faz_c_test_webhook_save.png`.

> Her değişiklik tenant başına izole edilir, audit log'a düşer (Bölüm 14'e bakın: Denetim).

---

## 13. Lisans & İade

### 13.1 14 gün koşulsuz iade

Self-Host: 14 gün içinde iade talep ederseniz tam ücret iade edilir, lisansınız Cloudflare Worker'da revoke edilir, ABS örneğiniz bir sonraki heartbeat'te (≤60 sn) chat çağrılarını reddetmeye başlar.

**İade prosedürü:**

1. `info@automatiabcn.com` adresine sipariş ID'nizi yazın.
2. 5 iş günü içinde Stripe iade işlemi başlar (kartınıza geri 5-10 iş günü sürebilir, bankaya bağlı).
3. Lisans token'ınız revoke edilir; backend `license_state.valid = False` durumuna geçer.
4. Yeni chat çağrıları 403 ile reddedilir; mevcut local config (admin parolası, RAG indeksi) bozulmaz.

### 13.2 Yenileme (Maintenance Pack)

12 ay sonra **isteğe bağlı** $49/yıl Maintenance Pack ile güncellemeler + email destek devam eder. Almazsanız ABS o anki sürümde sınırsız çalışmaya devam eder, ancak yeni image güncellemelerine erişim kapanır.

### 13.3 Lisans aktarımı

Donanım fingerprint binding **opsiyonel** yapılandırmadır (CJ-005). Founder mintinde fingerprint atanmadıysa (`machine_fp: null`), lisansı başka makineye taşıyabilirsiniz; CF Worker activation o anda yeni IP/fingerprint'i kaydeder.

---

## 14. Sorun giderme

| Belirti | Çözüm |
|---------|-------|
| `docker compose up -d` "exec format error" | Image rc4+ multi-arch — eski tag (rc1/rc2) Apple Silicon'da çalışmaz. `ABS_VERSION=1.0.0-rc4` set edin. |
| Caddy 502 / TLS hatası | Port 80+443 firewall'da açık olmalı (Let's Encrypt HTTP-01). `ufw allow 80,443/tcp`. |
| Setup Wizard "License signature invalid" | Founder mint imzası container public key ile uyumsuz olabilir; founder ile iletişime geçin. |
| Chat "license_invalid" 403 | Heartbeat lisansı revoke gördü. Lisans email'inizi kontrol edin veya yenileyin. |
| RAG sorgu boş sonuç | Doküman henüz indekslenmedi. `docker compose logs backend` → "embedding done" mesajı bekleyin. |
| Knowledge Graph "Internal Server Error" | Neo4j tenant init eksik olabilir. `docker compose restart` deneyin, sonra founder destek. |
| Email gelmedi | Spam klasörünü kontrol; SMTP relay yapılandırmanız varsa Settings → Webhook'lar → Email alerts. |
| Yüksek RAM kullanımı | Whisper/TTS modelleri opsiyonel; `.env`'de `ABS_DISABLE_TTS=1` ile kapatın. |

> Cevap bulamazsanız `info@automatiabcn.com` (24h yanıt) veya kendi support kanalınız.

---

## Yasal uyarılar & marka bildirimi

- **Automatia ABS™** Automatia BCN'in tescilli markasıdır.
- **Anthropic®, Claude®, Cohere®, Cerebras®, Groq®, Gemini™, Cloudflare®, Stripe®, Hetzner®, DigitalOcean®, Linode®, Vultr®, Slack®, Gmail™, Linear®, Notion®, PostgreSQL®, Neo4j®, Docker®, Caddy®, Let's Encrypt®** ilgili şirketlerin tescilli markalarıdır. Bu rehberdeki referanslar yalnızca müşteri tarafı entegrasyon bilgisidir; resmi ortaklık veya destek anlamına gelmez.
- Sağlayıcı API kullanımı **müşterinin kendi hesabından** ücretlendirilir. Automatia BCN bu ücretlerden pay almaz, fatura kesmez.
- Bu rehberdeki ekran görüntüleri Automatia BCN'in kendi UI'sıdır. Üçüncü taraf hizmet UI'larının (sağlayıcı konsolları, ödeme akışı dış kısımları) ekran görüntüleri rehbere dahil edilmemiştir; ilgili sağlayıcının dokümantasyonuna başvurun.
- ABS, BSL 1.1 lisansı kapsamında dağıtılır (`LICENSE` dosyası). 2030-05-07 itibariyle Apache License 2.0'a otomatik geçer.
- GDPR / KVKK kapsamında veri işleyici sıfatınızla **siz kendi sunucunuzda** kişisel verileri işlersiniz. Automatia BCN bu verilere erişmez. Veri saklama süreleri için Settings → Güvenlik.

---

**Son güncelleme:** 2026-05-09 · v1.0  
**İletişim:** info@automatiabcn.com  
**Source:** [github.com/automatiabcn/abs](https://github.com/automatiabcn/abs)  
**Made in Barcelona** 🇪🇸 — *Automate the chaos*
