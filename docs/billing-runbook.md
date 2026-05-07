# Stripe Billing Runbook

Bu doküman ABS billing altyapısını canlıya alma + günlük operasyon
sorumluluklarını tanımlar. Hedef kitle: solo operatör (Automatia BCN engineering).

---

## 1. Test Mode → Live Mode Geçişi

### 1.1 Stripe Dashboard hazırlık

1. Stripe Dashboard → Developers → API keys → "Live mode" toggle.
2. `Reveal live key` → `sk_live_...` kopyala (TEK SEFER GÖRÜNÜR — kaybedersen
   regenerate, eski key invalid).
3. `Webhooks` → "+ Add endpoint" → URL `https://abs.automatiabcn.com/webhooks/stripe`
   - Events: `checkout.session.completed`, `charge.refunded`,
     `customer.subscription.deleted`
   - Signing secret kopyala (`whsec_...`)

### 1.2 Vault'a yaz (013 — plaintext .env'e yazma)

```bash
ssh prod-server
cd /opt/abs
# Vault yolu konteyner içinden, age key /app/vault-key/age.pub
sops --age=$(cat /app/vault-key/age.pub) -e -i secrets/billing.enc.json
# Editör açılır → ABS_STRIPE_SECRET_KEY ve ABS_STRIPE_WEBHOOK_SECRET değerlerini
# `sk_live_...` ve `whsec_...` ile değiştir, kaydet.
docker compose restart abs-backend
```

Boot logları kontrol et:
```bash
docker compose logs abs-backend | grep -i "vault boot"
# beklenen: "vault boot: 2 secrets loaded into settings"
```

### 1.3 Live products oluştur

```bash
# Önce dry-run (idempotent kontrol):
ABS_STRIPE_SECRET_KEY=sk_live_... \
  python infra/scripts/setup_stripe_products.py --mode live --dry-run
# 3 satır WOULD-CREATE göreceksin.

# Sonra gerçek kayıt:
ABS_STRIPE_SECRET_KEY=sk_live_... \
  python infra/scripts/setup_stripe_products.py --mode live
# Çıkan ABS_PRICE_*=price_... satırlarını vault'a yaz.
```

Safeguard: script `--mode live` + `sk_test_` veya `--mode test` + `sk_live_`
kombinasyonunu görürse exit 2 + stderr ABORT mesajı yazar. Yanlış key ile
yanlış product oluşmaz.

### 1.4 İlk live test (kendi kart — küçük tutar)

1. `https://abs.automatiabcn.com/` → kendi email'inle "Buy Self-Host".
2. Test kartı yerine GERÇEK kart kullanılır (Stripe live mode test kart kabul
   etmez).
3. Stripe Dashboard → Payments → ödeme görüldü mü?
4. Email gelir → license key.
5. Setup wizard'a gir → activate → `mcp_require_license` toggle aç → MCP tool
   çalışmalı.

### 1.5 İlk live test'ten sonra

- Stripe Dashboard → ilgili Payment → "Refund payment" ile geri al ($0 net).
- Webhook event log'u kontrol et:
  ```bash
  docker compose exec abs-backend python -c "
  from app.db.session import get_session_sync
  from app.db.models import WebhookEvent
  from sqlmodel import select
  with get_session_sync() as db:
      for e in db.scalars(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(10)).all():
          print(e.event_type, e.event_id, e.processed_at, e.license_jti)
  "
  ```
- `License.revoked_at` doldu mu? `revoked_reason='stripe_refund'` mu?

---

## 2. Webhook Secret Rotate

Compromise şüphesi varsa veya CI'a yanlışlıkla bastıysan:
1. Stripe Dashboard → Webhooks → mevcut endpoint → `Roll secret`.
2. Yeni `whsec_...` vault'a yaz (1.2 adımı).
3. Backend restart.
4. Stripe Dashboard → "Send test webhook" ile doğrula (200 dönmeli).

---

## 3. Manual Refund (müşteri talebi)

Stripe Dashboard üzerinden yapılır:
1. Payments → ilgili ödeme → "Refund payment".
2. Reason: `customer_request` | `duplicate` | `fraudulent`.
3. Webhook otomatik tetiklenir → `License.revoked_at` set olur.
4. Refund email gönderilir (template: `license_refund.html`, 012).
5. Idempotency tablosu (017): aynı `event.id` tekrar gelirse `revoked_at`
   üzerine yazılmaz, audit temiz kalır.

---

## 4. Dispute / Chargeback

Stripe email gelir: "A dispute was opened on your charge."
1. Dashboard → Disputes → ilgili kayıt.
2. Evidence yükle: license_delivery email screenshot, customer activate log,
   yapılan API çağrıları (panel access logs).
3. Backend'de `License.revoked_at` MANUEL set et (chargeback ödeme alıkonur):
   ```python
   docker compose exec abs-backend python -c "
   from datetime import datetime, timezone
   from sqlmodel import select
   from app.db.session import get_session_sync
   from app.db.models import License
   with get_session_sync() as db:
       lic = db.scalars(select(License).where(License.customer_email=='X@Y.co')).first()
       lic.revoked_at = datetime.now(timezone.utc)
       lic.revoked_reason = 'stripe_chargeback'
       db.commit()
   "
   ```

---

## 5. Yaygın Hatalar

| Hata | Sebep | Çözüm |
|---|---|---|
| `503 Stripe yapılandırılmadı` | env yok / vault yüklenmedi | vault decrypt + restart |
| `400 İmza doğrulanamadı` | webhook secret yanlış | endpoint secret rotate, vault güncelle |
| `502 Stripe error: rate_limited` | API rate limit | exponential backoff, 30s sonra retry |
| `400 Payload geçersiz` | Stripe SDK version mismatch | `pip install -U stripe` |
| Refund webhook gelmiyor | Endpoint events list eksik | Dashboard → Webhooks → Events ekle |
| `404 Aktif lisans bulunamadı` (portal) | Müşteri farklı email | Dashboard'da `customer_id_stripe` ile cross-check |

---

## 6. Customer Portal (017)

`POST /v1/billing/portal` body `{customer_email}` ile Stripe Customer Portal
session URL döner (1 saat geçerli). Müşteri kendi self-service yapar:
- Cancel subscription
- Invoice history
- Payment method update
- Email alarm prefs

Hata kodları:
- `503` — Stripe key konfigüre değil.
- `404` — Aktif lisans yok / customer_id_stripe boş.
- `502` — Stripe API hatası (logs'a yazılır).

---

## 7. Günlük İzleme (15 dk/gün)

```bash
# MCP tool ile (önerilen, tek ekran):
ask "billing_status" gptoss

# DB direct:
sqlite3 /app/data/abs.db "SELECT event_type, COUNT(*) FROM webhook_events GROUP BY event_type"
sqlite3 /app/data/abs.db "SELECT tier, seat_count, COUNT(*) FROM licenses WHERE revoked_at IS NULL GROUP BY tier, seat_count"
```

Anormal pattern (alarm):
- `charge.refunded > 5%` → ürün/ödeme akışı sorunu, müşteri retention.
- `License.revoked_at` ortalama < 7 gün → demo/onboarding sorunu.
- `webhook_events.error NOT NULL` → handler bug, log incele.
- `billing_status.recent_events` 24 saatte hiç olay yoksa → site down olabilir.

---

## 8. Acil İletişim

- Stripe support: dashboard → Help → Contact (live mode prio: <2 saat).
- ABS backend log path: `/var/log/abs/backend.log` (013 audit JSONL).
- Vault yedek: `~/abs-vault-backup/age.key` (cold storage, ALSA git'e koymaz).
