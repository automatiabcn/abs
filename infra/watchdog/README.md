# ABS Central Watchdog

Bizim tarafta (Automatia BCN) çalışan cron servis — provider pricing/changelog değişikliklerini günde 1 kere tarar ve değişiklik tespit edilirse Discord webhook'una bildirir.

**Müşteri tarafına etkisi YOK** — bu servis backend container'ında çalışmaz, ABS sunucusunun bir parçası değildir.

## Deploy (Hetzner VPS, ~$5-10/ay)

```bash
# 1. VPS'e SSH bağlan
ssh root@watchdog.automatiabcn.com

# 2. Repo'yu kopyala (yalnızca infra/watchdog/)
mkdir -p /opt/abs-watchdog
rsync -avz infra/watchdog/ root@watchdog.automatiabcn.com:/opt/abs-watchdog/watchdog/

# 3. Python venv + bağımlılıklar
cd /opt/abs-watchdog
python3 -m venv .venv
.venv/bin/pip install httpx pyyaml

# 4. Discord webhook env (systemd EnvironmentFile veya doğrudan crontab)
echo 'WATCHDOG_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...' > /etc/abs-watchdog.env

# 5. crontab
crontab -e
# Ekle:
# 0 6 * * * cd /opt/abs-watchdog && set -a && . /etc/abs-watchdog.env && set +a && .venv/bin/python -m watchdog.cron >> /var/log/abs-watchdog.log 2>&1
```

## MVP Scope (014)

- ✅ İskelet (`scanner.py`, `alerter.py`, `cron.py`) — import çalışıyor
- ✅ `scan_all()` 6 provider için stub döner
- ✅ `send_discord_alert()` webhook yoksa False döner (exception yok)

## 015 Eklenen

- ✅ `deploy.sh` — Hetzner / DO VPS otomatik kurulum scripti (Python venv + cron + logrotate)
- ✅ `docs/operations.md § 11` — VPS kurulum talimatı + Discord webhook setup
- ✅ `docs/operations.md § 12` — Manifest release flow (signing + S3 upload)

## 016+ Scope

- Provider başına gerçek HTML scrape parser (BeautifulSoup veya lxml)
- Önceki snapshot ile diff (cache JSON dosyası)
- Email alert (SMTP) opsiyonu
- Kritik fiyat değişiklikleri için multiple alert kanalı
- ABS müşterileri için panel'de "model deprecated" uyarı entegrasyonu

## Manifest Signing Flow (Bizim Taraf)

Yeni release yayını adımları (`docs/operations.md § 12` detaylı):

```bash
# 1) Manifest hazırla
vim manifest.json

# 2) İmzala (1Password'dan private.pem çıkar)
openssl dgst -sha256 -sign manifest-keys/private.pem -out manifest.json.sig.bin manifest.json
base64 manifest.json.sig.bin > manifest.json.sig

# 3) S3'e upload
aws s3 cp manifest.json     s3://abs-releases/manifest.json
aws s3 cp manifest.json.sig s3://abs-releases/manifest.json.sig
```

Müşteri tarafında `app/update/manifest_pubkey.pem` ile fail-closed verify yapılır.
