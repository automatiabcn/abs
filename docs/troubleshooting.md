# Troubleshooting

ABS'i kurarken ya da çalıştırırken karşılaşabileceğin yaygın hatalar ve çözümleri.

## Landing routes 404 after adding a new page

**Symptom:** `/pricing`, `/beta`, etc. return 404 in `next dev` even though `app/<route>/page.tsx` exists.

**Cause:** stale `.next/` build cache after a new App Router page is added.

**Fix:**

```bash
cd core/landing
rm -rf .next
npx next dev
```

**Verification:** `npm run test:e2e` (Playwright suite at `__tests__/playwright/routes.spec.ts`) probes every public route for status 200 and no console errors.

## Vault / sops

### `vault disabled (binary or master key missing)`

**Sebep:** Container içinde `sops` veya `age` binary'leri eksik, veya
`/app/vault-key/age.txt` mount edilmemiş.

**Çözüm:**
```bash
docker compose exec backend which sops age   # ikisi de bulunmalı
ls -la vault-key/age.txt                     # host tarafında dosya var mı?
docker compose down && docker compose up -d  # mount yenilensin
```

`age.txt` içeriği `# created: ...` ve `AGE-SECRET-KEY-1...` satırlarını içermeli.

### `sops: failed to decrypt`

**Sebep:** age public key (.env'deki `ABS_VAULT_AGE_PUBLIC_KEY`) ile
şifrelenen secret farklı bir public key ile encrypt edildi.

**Çözüm:** `vault-key/age.txt` dosyasından doğru public key'i çıkar
(`grep public-key vault-key/age.txt`). `.env`'yi güncelle, restart.

## Stripe webhook

### `400 Stripe-Signature header eksik`

**Sebep:** Webhook endpoint'i Stripe'tan değil başka bir client'tan geldi.

**Çözüm:** Stripe Dashboard → Webhooks → endpoint URL'i `/webhooks/stripe`
olarak doğrula. Test webhook gönder.

### `400 İmza doğrulanamadı`

**Sebep:** `ABS_STRIPE_WEBHOOK_SECRET` yanlış. Live mode'a geçişte secret
değişmiş olabilir.

**Çözüm:** Stripe Dashboard → Webhooks → endpoint detail → `Roll secret`
veya görüntüle → vault'a yaz → backend restart.

### Refund webhook gelmiyor

**Sebep:** Stripe Dashboard → Webhooks → endpoint events listesinde
`charge.refunded` ekli değil.

**Çözüm:** Endpoint detail → Add events → `charge.refunded` + `customer.subscription.deleted`
seç. Test webhook gönder.

## MCP / Claude Code

### `[LISANS GEREKLI] ABS şu anda lisans gerektiriyor`

**Sebep:** `ABS_MCP_REQUIRE_LICENSE=true` ama lisans yok / demo süresi dolmuş.

**Çözüm:** Setup wizard'a gir → lisans aktive et. Demo'yu uzatmak istiyorsan
`/app/data/demo_state.json` dosyasını silip restart et (14 gün başlar).

### `MCP tool not found: ask_xyz`

**Sebep:** Tool registry'de yok. Versiyon güncel olmayabilir.

**Çözüm:**
```bash
docker compose exec backend python -c \
  "from app.mcp.server import mcp_server; import asyncio; \
   tools = asyncio.run(mcp_server.list_tools()); \
   print(sorted(t.name for t in tools))" | grep ask_xyz
```

Boş çıkıyorsa `git pull && docker compose pull && docker compose up -d`.

### Claude Code MCP bağlanmıyor

**Sebep:** URL'de `/mcp` path'i eksik veya HTTPS yok.

**Çözüm:**
```bash
claude mcp remove abs
claude mcp add abs https://abs.firmaadi.com/mcp
claude mcp list   # status: connected olmalı
```

## Provider hataları

### `circuit_breaker_open: anthropic`

**Sebep:** Anthropic API son 5 dakikada üst üste 5 hata verdi (014 cascade).

**Çözüm:**
```bash
ask "breaker_status" gptoss   # state'i incele
# manuel reset:
docker compose exec backend python -c \
  "from app.cascade.breaker import reset_breaker; reset_breaker('anthropic')"
```

Anthropic status sayfasına bak: `status.anthropic.com`.

### `rate_limited: groq`

**Sebep:** Groq free tier rate limit (TPM 6000).

**Çözüm:** `qual-code` / `race` gibi paralel pipeline'lar yerine `kimi` veya
`gptoss` tek-shot kullan. Veya Groq Dev Tier'a yükselt.

### Email gönderilmiyor

**Sebep:** `ABS_SMTP_HOST` boş — console fallback aktif (loglara yazıyor).

**Çözüm:** Real SMTP yapılandır:
```ini
ABS_SMTP_HOST=smtp.resend.com
ABS_SMTP_PORT=587
ABS_SMTP_USER=resend
ABS_SMTP_PASSWORD=re_xxxxxxxx
ABS_SMTP_FROM=noreply@firmaadi.com
```

`docker compose logs email-cron | tail -20` ile tick çıktısını izle.

## Database

### `sqlite3.OperationalError: database is locked`

**Sebep:** SQLite WAL'a yazarken iki process aynı anda erişti
(çok nadir, genelde cron + manual query çakışması).

**Çözüm:** Genelde 1-2sn'de geçer. Süreklise:
```bash
docker compose exec backend sqlite3 /app/data/abs.db "PRAGMA journal_mode=WAL;"
```

### `no such table: webhook_events`

**Sebep:** Migration boot'ta çalışmadı (çok eski versiyondan upgrade).

**Çözüm:**
```bash
docker compose exec backend python -c \
  "from app.db.session import init_db; init_db()"
```

## Setup Wizard

### Setup yarıda kaldı, panel açılmıyor

**Sebep:** First-run middleware aktif, `setup_state.json` `completed:false`.

**Çözüm:** `/setup`'a git, kaldığın yerden devam. Veya manuel:
```bash
docker compose exec backend python -c \
  "import json, time, pathlib; \
   p = pathlib.Path('/app/data/setup_state.json'); \
   p.write_text(json.dumps({'completed':True,'current_step':6,'completed_steps':['admin','license','domain','anthropic','providers','test'],'started_at':time.time(),'completed_at':time.time(),'data':{}}))"
```

## Cerbos / Helm

### `helm upgrade abs` Cerbos pod'u CrashLoopBackOff'a düşüyor (Caveat #12)

**Sebep:** Q12-R76 öncesi `infra/helm/abs/values*.yaml` Cerbos için K8s
1.27/1.28/1.29 ile uyumlu olmayan field'lar tutuyordu (`policy_compile_failed`).
R76 helm umbrella + R89 production deploy spec bu sorunu kapatır.

**Çözüm:**

```bash
cd infra/helm/abs
helm upgrade --install abs . \
    --namespace abs-prod \
    --values values.production.yaml \
    --atomic --timeout 5m
```

**Doğrulama (R89 4-adım):**

1. `kubectl -n abs-prod rollout status deployment/abs-cerbos`
2. `kubectl -n abs-prod logs deployment/abs-cerbos --tail 50` — `policy_compile_failed` görünmemeli
3. `kubectl -n abs-prod exec deployment/abs-api -- curl -s localhost:3592/_cerbos/healthz` → `{"status":"SERVING"}`
4. `kubectl -n abs-prod exec deployment/abs-api -- curl -s localhost:3592/api/check` örnek policy isteği → 200

Detay: `artifacts/sprint_q12/round_89_cerbos_live_deploy_spec.md`.

## Lighthouse nightly cron

### Cron 0 fail / artefakt boş (`abs.local` resolution)

**Sebep:** Q12-R82 öncesi `lighthouse-nightly.yml` workflow'u
`http://abs.local`'i probe ediyordu — CI runner DNS'inde resolve etmiyor,
job sessizce fail oluyordu.

**Çözüm:** R82 (`f362601`) hedefi `http://localhost:3000`'e çevirdi.
İlk post-fix Saturday cron: **2026-05-09 02:00 UTC**.

**Doğrulama:**

```bash
ls -lah artifacts/lighthouse/2026-05-09T02-*.json
jq '.categories | {perf:.performance.score, a11y:.accessibility.score, bp:."best-practices".score, seo:.seo.score}' \
   artifacts/lighthouse/2026-05-09T02-*.json
```

4 × 1.0 (perf/a11y/bp/seo) bekleniyor. < 0.9 düşerse bug aç ve handoff'u
durdur. Review template:
`artifacts/sprint_q12/round_90_lighthouse_artifact_review.md`.

## Bilinmeyen hatalar

`docker compose logs backend | tail -100` çıktısını
`support@automatiabcn.com` adresine gönder. Maintenance müşterileri için 24h
yanıt; diğerleri için 48h.

İhtiyacın olabilecek diğer kaynaklar:

- [FAQ](faq.md) — kısa cevaplar
- [Setup Guide](setup-guide.md) — sıfırdan kurulum
- [API Reference](api-reference.md) — MCP tool listesi
