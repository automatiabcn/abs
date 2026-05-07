# Setup Guide — 15 dakikada ABS kur

Bu rehber Automatia ABS'i sıfırdan production-ready bir self-host kurulumu olarak kuruyor.
Kurulumu 15 dakikada bitirmek için **Docker Compose** kullanıyoruz; manuel kurulum
sonu (`pip install`) için son bölüme bakın.

## Önkoşullar

- Linux sunucu (Ubuntu 22.04+, Debian 12, veya AlmaLinux 9 — 1 vCPU, 2 GB RAM, 20 GB disk yeterli).
- Docker Engine 24+ ve Docker Compose v2 (`docker compose version`).
- DNS A kaydı: `abs.firmaadi.com` → sunucu IP.
- Açık portlar: 80 + 443.
- Anthropic API anahtarı (`sk-ant-...`) — [console.anthropic.com](https://console.anthropic.com/).
- Stripe live key (`sk_live_...`) ve webhook secret (`whsec_...`) — opsiyonel,
  kendi ödeme akışın için.

## Adım 1 — Lisans ve repo

ABS'i satın al — `https://abs.automatiabcn.com/` üzerinden Stripe Checkout. Email ile
gelen lisans anahtarını sakla; setup wizard'a Adım 4'te girmen gerekecek.

```bash
git clone https://github.com/automatiabcn/abs.git
cd abs/infra
cp .env.example .env
```

`.env` dosyasında en az şu değeri doldur:

```ini
ABS_LICENSE_KEY=eyJhbGciOiJSUzI1NiIs...   # email'den geldi
ABS_DOMAIN=abs.firmaadi.com
ABS_ADMIN_EMAIL=admin@firmaadi.com
ABS_ADMIN_PASSWORD_BOOTSTRAP=ilk-girisiniz-icin-gecici-sifre
```

## Adım 2 — Vault başlat (sops/age)

Stripe + Anthropic secret'larını disk üzerinde plaintext bırakmamak için **sops + age**
vault aktiftir (013):

```bash
# age master key oluştur (TEK SEFER — yedek al, kaybolursa vault sıfırdan)
mkdir -p vault-key
docker run --rm -v $(pwd)/vault-key:/k alpine \
    sh -c "apk add --no-cache age && age-keygen -o /k/age.txt && cat /k/age.txt | grep public"

# public key çıktısını kopyala → ABS_VAULT_AGE_PUBLIC_KEY .env'ye yaz
echo "ABS_VAULT_AGE_PUBLIC_KEY=age1xxxxx..." >> .env
```

Yedek planı: `vault-key/age.txt` dosyasını 1Password / Bitwarden gibi şifreli vault'a yedekle.
Kaybolursa şifreli secret'lara erişimini kaybedersin.

## Adım 3 — Docker Compose ile başlat

```bash
docker compose up -d
docker compose ps
```

3 service ayağa kalkmalı:

| Service | Port | Sağlık |
|---|---|---|
| `backend` | 8000 (internal) | `curl localhost:8000/healthz` → 200 |
| `email-cron` | — | logs `sent=N failed=M` her 5dk |
| `caddy` | 80, 443 | otomatik HTTPS Let's Encrypt |

## Adım 4 — Setup wizard (6 adım, ~5dk)

`https://abs.firmaadi.com/setup` adresine git. ABS first-run middleware seni otomatik buraya yönlendirecek.

1. **Admin hesabı** — email + bcrypt'le saklanacak şifre.
2. **Lisans** — Adım 1'de aldığın `ABS_LICENSE_KEY`. Online doğrulama yok; JWT RS256 imzalı.
3. **Domain** — bir önceki adımda yazdığın `ABS_DOMAIN` (otomatik dolu).
4. **Anthropic API** — `sk-ant-...` anahtarı vault'a şifreli yazılır.
5. **Provider'lar** — Groq / Cerebras / Gemini / Cohere / Cloudflare API key'leri.
   Hepsi opsiyonel — boş bırakırsan o sağlayıcı circuit breaker tarafından devre dışı
   kalır.
6. **Test** — `system_status` MCP tool çalışır; provider sağlık ve cache durumu gelir.

Setup tamamlanınca `setup_state.json` `completed:true` olur ve middleware `/panel`'e yönlendirir.

## Adım 5 — Claude Code'a bağla

Claude Code'da MCP server ekle:

```bash
claude mcp add abs https://abs.firmaadi.com/mcp
```

Test et:

```bash
ask "system_status" gptoss
```

Beklenen JSON çıktısı: 100+ tool registered, 6 provider configured, vault loaded.

## Adım 6 — Stripe billing (opsiyonel, kendi ödeme akışın için)

Kendi müşterilerine ABS satıyorsan Stripe altyapısını da etkinleştir:

1. `https://dashboard.stripe.com` → Developers → API keys → live key kopyala.
2. Webhook endpoint ekle: `https://abs.firmaadi.com/webhooks/stripe`. Events:
   `checkout.session.completed`, `charge.refunded`, `customer.subscription.deleted`.
3. Vault'a yaz:
   ```bash
   sops --age=$(cat vault-key/age.pub) -e -i secrets/billing.enc.json
   # editor: ABS_STRIPE_SECRET_KEY ve ABS_STRIPE_WEBHOOK_SECRET
   docker compose restart backend
   ```
4. Live products oluştur:
   ```bash
   ABS_STRIPE_SECRET_KEY=sk_live_... \
     python infra/scripts/setup_stripe_products.py --mode live
   ```
5. İlk live test (kendi kart) → Dashboard'dan refund.

Ayrıntı: [Billing Runbook](billing-runbook.md).

## Adım 7 — Backup ve monitoring

Günde 1 cron önerilir:

```bash
# /etc/cron.daily/abs-backup
docker compose exec backend tar czf /tmp/abs-$(date +%F).tar.gz /app/data
mv /tmp/abs-*.tar.gz /var/backups/abs/
find /var/backups/abs -mtime +30 -delete
```

Monitoring için `health_status` MCP tool'unu Cloudflare Worker veya UptimeRobot'a
bağla — provider down olursa Slack alert.

## Adım 8 — Güncelleme

Yeni versiyon çıktığında:

```bash
cd abs/infra
git pull
docker compose pull && docker compose up -d
docker compose logs backend | tail -50    # migration log'u kontrol et
```

ABS update channel signature ile imza doğrular (014). Bozuk imzayı reddeder.

## Fresh Install — test/QA verilerini temizle

Repo'da geliştirme + QA sırasında üretilmiş test admin'leri, sohbet geçmişi
ve örnek RAG dosyaları bulunabilir (örnek: `l24scan@test.local`, `tester-…@digisfer.local`).
Production handoff'tan önce bu verileri temizle:

```bash
# 1) Önce dry-run — neyin silineceğini gör
docker compose exec backend python /app/scripts/audit_test_data.py
#   → JSON çıktı + artifacts/test_data_audit.md

# 2) Onayladıktan sonra confirm
docker compose exec backend python /app/scripts/reset_test_data.py --confirm --purge-rag
```

**Otomatik (ilk açılış):** `.env` içine `ABS_FRESH_INSTALL=true` ekleyip
`infra/scripts/first-boot-reset.sh` script'ini çalıştır — script flag'i kontrol eder,
gerçek müşteri kurulumlarında atlanır:

```bash
ABS_FRESH_INSTALL=true bash infra/scripts/first-boot-reset.sh
```

Kurallar:

- `admin@demo-acme.com` (bootstrap admin) ve `system@abs.local` **silinmez**.
- `tier ∈ {self-host, team, enterprise}` lisansları **silinmez** (sadece `beta`).
- Real-customer tenant verisi (`demo-acme`, `default`) için tüm silmeler
  per-row email pattern bazlı; tenant-only sweep yapılmaz.
- İkinci `--confirm` çalıştırması idempotent: `total_deleted == 0`.

## Sonraki adımlar

- [API Reference](api-reference.md) — 100+ MCP tool
- [Troubleshooting](troubleshooting.md) — yaygın hatalar
- [FAQ](faq.md) — kısa cevaplar

Kuruluma yardım gerekiyorsa `support@automatiabcn.com` — Maintenance müşterileri için 24h SLA.
