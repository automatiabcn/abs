# ABS Operasyonları

Bu belge, Automatia ABS'nin operasyonel süreçlerini, izleme mekanizmalarını ve bakım rutinlerini detaylandırmaktadır. Amaç, sistemin istikrarlı ve güvenilir çalışmasını sağlamak için gerekli adımları ve mimariyi açıklamaktır.

## 1. Operasyon Özeti

ABS operasyonları, merkezi bir izleme sistemi (Central Watchdog) ve müşteri tarafında çalışan sağlık izleme mekanizmaları üzerine kuruludur. Temel hedefler, sağlayıcı değişikliklerini proaktif olarak tespit etmek, sistem güncellemelerini sorunsuz bir şekilde dağıtmak ve olası kesintilere karşı otomatik yedekleme ve tolerans sağlamaktır. Müşteri, kendi kendine barındırma modelinde sistemin yedeklemesinden sorumludur. Destek, e-posta ve ilerleyen aşamalarda Discord üzerinden sağlanacaktır.

## 2. Central Watchdog Mimarisi ve Akışı

Central Watchdog, ABS'nin merkezi izleme ve uyarı sistemidir.

- **Tip**: Python cron servis
- **Çalışma Sıklığı**: Günlük 06:00 (UTC)
- **Barındırma**: Hetzner $5-10/ay VPS
- **URL**: `abs.automatiabcn.com/watchdog/` (internal, sadece bizim erişim)
- **İzlenen Sağlayıcılar**: 6 farklı sağlayıcı (Anthropic, Groq, Cerebras, CloudFlare, Gemini, Cohere)

### İzleme Detayları

Her bir sağlayıcı için aşağıdaki veriler taranır:

- **Fiyatlandırma Sayfası**: HTML içeriğindeki değişiklikler için diff kontrolü.
- **Changelog**: RSS beslemeleri (Anthropic, OpenAI, Groq GitHub, Gemini).
- **Durum JSON**: Sağlayıcının durum API'si (örn. `status.anthropic.com/api/v2/summary.json`).
- **Sentetik Test Çağrısı**: Sağlayıcının API'sine yapılan gerçek bir test çağrısı.

### Akış

1. Watchdog, günlük olarak belirtilen saatte tüm sağlayıcıları tarar.
2. Tarama sonucunda herhangi bir değişiklik (fiyatlandırma, changelog, durum veya sentetik testte anormallik) tespit edilirse:
   - Discord ve e-posta yoluyla bir uyarı tetiklenir.
   - Yeni bir ABS release'i hazırlığı başlatılır.

## 3. Update Channel — Release Süreci

ABS, sağlayıcı yapılandırmalarını ve sistem güncellemelerini **Update Channel** üzerinden yönetir.

- **Yapılandırma Dosyaları**: Bizim repo içinde `infra/provider-configs/*.yaml`
- **İçerik**: Her sağlayıcı için model takma adları (aliases), fiyatlandırma meta verileri, sağlık uç noktaları ve bilinen limitler.
- **Güncelleme**: Her ABS release'inde bu klasördeki dosyalar güncellenir.
- **Müşteri Güncellemesi**: Müşteriler `docker-compose pull` komutunu çalıştırdığında, yeni yapılandırmalar otomatik olarak gelir.
- **Kritik Değişiklikler**: Çok kritik değişiklikler durumunda, bir hotfix release yayınlanır ve müşterilere e-posta ile bilgilendirme yapılır.

### Müşteri Güncelleme Mekanizması

- **Bildirim**: ABS panelinde "Update available v1.x.y" bildirimi görünür.
- **Sürüm Notları**: Bildirimde release notlarına bir bağlantı bulunur.
- **Güncelleme Adımı**: Tek tıklama ile güncelleme (`docker-compose pull && up -d`) mümkündür.
- **Breaking Changes**: Geriye dönük uyumsuz değişiklikler için manuel migration scriptleri sağlanır ve dokümante edilir.

## 4. Müşteri Serviste Health Monitor

Her ABS müşterisinin kendi kurulumunda çalışan bir sağlık izleme mekanizması bulunur.

- **Sıklık**: Her 60 saniyede bir, her sağlayıcıya sentetik bir çağrı (ping) yapılır.
- **Durumlar**:
  - `ok`: Sağlayıcı sorunsuz çalışıyor.
  - `degraded`: Sağlayıcıda performans düşüşü veya kısmi sorunlar var.
  - `down`: Sağlayıcı erişilemez durumda.
- **Panel Gösterimi**: Müşteri panelinde durum, renkli bir banner ile gösterilir (yeşil/sarı/kırmızı).
- **Otomatik Fallback**: Bir sağlayıcı `down` durumuna geçtiğinde, sistem otomatik olarak diğer uygun sağlayıcılara geçiş yapar (cascade otomatik fallback). Bu geçiş kullanıcı için sessizdir.

## 5. Circuit Breaker ve Semantic Cache

ABS, sistemin dayanıklılığını artırmak için Circuit Breaker ve Semantic Cache mekanizmalarını kullanır.

### Circuit Breaker

- **Tetikleme**: Belirli bir sağlayıcıdan 1 dakika içinde 5 hata alınması durumunda, sağlayıcı "open" (açık) durumuna geçer.
- **Reset Timeout**: "Open" durumundaki bir sağlayıcı 60 saniye boyunca istek almaz. Bu sürenin sonunda "half-open" (yarı açık) durumuna geçer.
- **Half-Open**: "Half-open" durumunda, sağlayıcıya tek bir test isteği gönderilir.
  - Test başarılı olursa, sağlayıcı tamamen "closed" (kapalı) durumuna döner ve tam kurtarma sağlanır.
  - Test başarısız olursa, sağlayıcı tekrar "open" durumuna döner ve reset timeout yeniden başlar.
- **Loglama**: Tüm Circuit Breaker durum değişiklikleri ve olayları loglara yazılır.

### Semantic Cache

- **TTL (Time-To-Live)**: 5 dakika.
- **Anahtar**: Prompt'un SHA-256 hash'i kullanılır.
- **Graceful Degradation**: Bir sağlayıcı bozulduğunda veya erişilemez olduğunda, sistem önbellekten dönen sonuçları kullanarak hizmeti sürdürmeye çalışır.

## 6. 4-Katmanlı Müşteri Garanti Modeli

ABS, müşteri hizmet sürekliliğini sağlamak için dört katmanlı bir garanti modeli sunar:

1. **Bir sağlayıcı düştü**: Sistem otomatik olarak diğer sağlayıcılara geçiş yapar (cascade otomatik fallback). Kullanıcıların %99'u bu durumu fark etmez.
2. **Bir sağlayıcı kullanımdan kaldırıldı (deprecated)**: ABS, sağlayıcı soyutlaması (abstraction) ve otomatik güncelleme mekanizmaları sayesinde bu durumu yönetir. Müşteri müdahalesi genellikle gerekmez.
3. **Free tier kaldırıldı**: Panelde bir banner bildirimi gösterilir ve alternatif sağlayıcılar veya çözümler sunulur.
4. **Tüm sağlayıcılar düştü**: Sistem önbellekten (cache) yanıt dönmeye çalışır. Ek olarak, müşteri kendi Anthropic API anahtarı ile doğrudan Anthropic'i kullanabilir.

## 7. Solo Operatör Haftalık Rutini

ABS'nin operasyonel sürdürülebilirliği için solo operatör tarafından yürütülen haftalık rutinler:

- **Pazartesi Sabah (30 dk)**: Central Watchdog raporları incelenir.
- **Topluluk Sinyalleri**: r/LocalLLaMA, Hacker News (HN) ve sağlayıcıların Discord kanalları taranarak olası sorunlar veya önemli gelişmeler takip edilir.
- **Hotfix Hazırlığı**: Gerekirse, tespit edilen sorunlar için hotfix release'leri hazırlanır.
- **Hafta İçi Otomatik**: Watchdog'dan herhangi bir uyarı gelmediği sürece, hafta içi manuel müdahale gerekmez.

## 8. Loglar ve İzleme

ABS, sistemin durumu ve performansı hakkında detaylı bilgi sağlamak için çeşitli loglar ve izleme metrikleri toplar:

- **Audit Log**: Kimin, ne zaman, hangi işlemi yaptığını kaydeder.
- **Provider Health Log**: Sağlayıcıların sağlık durum geçmişini tutar.
- **Cache Hit/Miss Counter**: Önbellek isabet ve kaçırma oranlarını izler.
- **Workflow Durability State (SQLite)**: İş akışlarının dayanıklılık durumunu SQLite veritabanında saklar.
- **Judge Log**: Skorlama geçmişini kaydeder.

## 9. Yedekleme

ABS, self-host bir ürün olduğu için yedekleme sorumluluğu müşteriye aittir.

- **Veri**: Varsayılan kurulum SQLite veritabanını (`/app/data/abs.db` — kiracı, kullanıcı, OAuth ve denetim zinciri) ve `age-encrypted secrets` dosyasını (`/app/data/secrets.yaml`) kullanır.
- **Araç (yedekle)**: `scripts/dr/backup_sqlite.sh` — çalışan veritabanından **tutarlı** bir anlık görüntü alır (SQLite `.backup` API'si; volume'ün `tar`'lanması yarım yazılmış sayfa → bozuk geri-yükleme riski taşır) ve `abs.db` + `secrets.yaml`'ı zaman damgalı bir `.tar.gz`'ye paketler. Container içinden veya host'tan çalışır (`docker compose exec backend ...`).
- **Araç (geri-yükle)**: `scripts/dr/restore_sqlite.sh <bundle>` — geri-yüklemeden önce mevcut DB'yi `abs.db.pre-restore-<tarih>`'e kopyalar, bütünlük kontrolü yapar, canlı DB'yi (`-wal/-shm`) tespit edip korumasız geri-yüklemeyi reddeder.
- **Vault anahtarı**: `secrets.yaml` şifreli kalır; çözmek için age vault anahtarı gerekir. Bu anahtarı **ayrı ve güvenli** yedekleyin — şifreli secrets'ın yanına koymak şifrelemeyi anlamsız kılar.
- **Detaylı runbook**: `docs/dr-runbook.md` (SQLite varsayılan kurulum + Postgres ölçekli kurulum).

## 10. Destek Kanalı

Müşterilere sunulan destek kanalları:

- **E-posta**: `support@automatiabcn.com`
- **Öncelikli Ücretli Destek**: Bakım aboneleri için 48 saat içinde yanıt garantisi.
- **Topluluk**: Faz 2 ve sonrasında Discord kanalı üzerinden topluluk desteği sağlanacaktır.

## 11. Watchdog Deploy (Hetzner) — 015

ABS Central Watchdog, **bizim tarafta** çalışan bağımsız bir cron servisidir. Provider pricing/changelog değişikliklerini günde 1 kez tarar, değişiklik tespit edilirse Discord webhook'una bildirir. Müşteri ABS sunucusunda çalışmaz.

### VPS Spec
- Hetzner CX11 (~€4/ay, 2vCPU, 4GB RAM, 40GB SSD) yeterli.
- Alternatif: DigitalOcean smallest droplet (~$6/ay).

### DNS
- A record: `watchdog.automatiabcn.com → <VPS IP>` (opsiyonel, SSH erişimi için).

### Kurulum
```bash
# 1) VPS hazırla (Ubuntu 22.04+)
ssh root@<vps-ip>

# 2) deploy.sh çalıştır (env override ile)
DISCORD_WEBHOOK="https://discord.com/api/webhooks/..." \
INSTALL_DIR=/opt/abs-watchdog \
WATCHDOG_USER=watchdog \
bash /tmp/deploy.sh

# 3) Kod yükle
git clone https://github.com/automatia/abs /opt/abs-watchdog/src
# veya scp infra/watchdog/* root@vps:/opt/abs-watchdog/src/watchdog/

# 4) Test çalıştırma
sudo -u watchdog bash -c "cd /opt/abs-watchdog/src && \
  WATCHDOG_DISCORD_WEBHOOK='https://...' \
  .venv/bin/python -m watchdog.cron"

# 5) Cron logları
journalctl -t abs-watchdog -f
```

`deploy.sh` aşağıdakileri yapar:
- `watchdog` user oluşturur (system user)
- Python venv + httpx/pyyaml install
- `/etc/cron.d/abs-watchdog` cron entry (06:00 UTC)
- `/etc/logrotate.d/abs-watchdog` weekly rotate

### Discord Webhook Setup
1. Discord sunucusunda channel → Edit Channel → Integrations → Webhooks → New Webhook
2. URL'i kopyala (`https://discord.com/api/webhooks/<id>/<token>`)
3. `deploy.sh` çalıştırırken `DISCORD_WEBHOOK=<url>` env'i geç

## 12. Manifest Release Flow — 015

Yeni ABS sürümü yayını için **bizim taraf**ta gereken adımlar (private key gizli):

```bash
# 1) Yeni release manifest hazırla
cat > manifest.json <<EOF
{
  "current_version": "0.2.0",
  "released_at": "2026-04-30T00:00:00Z",
  "channel": "stable",
  "min_version": "0.1.0",
  "critical": false,
  "changelog_url": "https://abs.automatiabcn.com/releases/0.2.0",
  "changelog_summary": "RAG hybrid + ML persona training",
  "docker_image": "ghcr.io/automatia/abs-backend:0.2.0",
  "breaking": false
}
EOF

# 2) İmzala (private.pem 1Password'da, çıkarıp kullan)
openssl dgst -sha256 -sign manifest-keys/private.pem -out manifest.json.sig.bin manifest.json
base64 manifest.json.sig.bin > manifest.json.sig

# 3) Release sunucusuna upload
aws s3 cp manifest.json     s3://abs-releases/manifest.json
aws s3 cp manifest.json.sig s3://abs-releases/manifest.json.sig

# 4) Test
curl https://abs.automatiabcn.com/releases/manifest.json
curl https://abs.automatiabcn.com/releases/manifest.json.sig
```

Müşteri tarafında `app/update/manifest_pubkey.pem` ile fetch sırasında verify edilir; signature doğrulanamazsa `state="unknown"` döner (fail-closed). `update_signature_required=False` sadece dev/test'te kullanılır.

### Master Key Sahipliği
- **Private key** (`manifest-keys/private.pem`) — Automatia BCN ekibinin sahip olduğu **TEK ANAHTAR**. 1Password / hardware token / encrypted offsite saklayın.
- Repo'ya commit YASAK (`.gitignore` `manifest-keys/`).
- Anahtar kayıp = release imzalama imkansız → key rotation flow (yeni key gen + müşterilere yeni `manifest_pubkey.pem` push, breaking update).

---

Uygulama detayları `_agent-tasks/` altında task bazlı yazılacak.
