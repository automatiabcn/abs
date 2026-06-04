# ABS — Yeni Sürüm Yükseltme Kılavuzu

> Bu sürüm güvenlik + kullanıcı-yönetimi + MCP düzeltmeleri içerir. Müşteri
> hiçbir config dosyasını **elle açıp düzenlemez**; aşağıdaki adımlar dosya
> *değiştirme* (yenisini çekme) + komut çalıştırmadan ibarettir.

## Bu sürümde ne değişti

**Güvenlik (kritik):**
- 🔒 **Vault encryption-at-rest artık gerçekten çalışıyor.** Önceki sürümde sops
  yanlış format (`--input-type` eksik) nedeniyle sağlayıcı anahtarlarını şifreli
  vault'a yazamıyor, sessizce plaintext `.env`'e düşüyordu. Artık anahtarlar
  şifreli `secrets.yaml`'da saklanıyor.
- 🔒 **`/mcp` artık token zorunlu kılıyor.** Token'sız erişim 401. (Önceden
  token enforce edilmiyordu — herkes 122 aracı çağırabiliyordu.)
- 🔒 **MCP token scope enforce ediliyor** (`hooks` scope'lu token `/mcp`'yi
  kullanamaz).
- 🔒 **`rag_index` yol kısıtlaması** — keyfi sunucu dosyası (vault key, DB,
  `/etc`) indekslenemez (path-traversal kapatıldı).
- 🔒 **Güvenlik header'ları** (X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, HSTS) Caddy'ye eklendi.

**Kullanıcı yönetimi:**
- Davet akışı: SMTP yoksa **kopyalanabilir aktivasyon linki** döner (artık
  davet maili "gitti" yalanı yok).
- **Çok-admin RBAC**: bir kullanıcıyı panelden Admin yapmak gerçek admin yetkisi
  verir; demote anında geri alır. Son aktif admin korunur. Self-signup artık
  `member` (admin değil) — yetki yükseltme kapatıldı.
- Yeni **MCP Token sayfası** (`/admin/mcp-tokens`) — token üret + Claude Code /
  Codex çalıştırma komutu + revoke.

**Otomasyon:**
- **vault-init** servisi — vault anahtarını ilk açılışta otomatik üretir
  (manuel `init_vault.sh` adımı kalktı).
- Cascade free-first (groq/gemini/... → anthropic son). Ekstra Anthropic
  anahtarı gerekmez.

## Yükseltme adımları (müşteri)

| Adım | Komut | Elle dosya düzenleme? |
|------|-------|-----------------------|
| 1. Yeni compose + .env şablonunu çek | `git pull` *veya* yeni `docker-compose.customer.yml` indir | Hayır (dosyayı değiştir) |
| 2. Yeni image'ları çek | `docker compose pull` | Hayır |
| 3. Stack'i güncelle | `docker compose up -d` | Hayır |

> **Neden compose'u da güncellemek gerekiyor?** `vault-init` servisi image'de
> değil **compose dosyasında** tanımlı. Sadece `docker compose pull` (image)
> yeterli değil — yeni compose dosyasını da almalısınız.

### MCP bağlantısı (Claude Code / Codex)
- **Zaten token ile bağlandıysanız: hiçbir şey yapmanıza gerek yok.** Token'lar
  `ABS_SESSION_SECRET` değişmediği sürece geçerli kalır.
- Token'sız bağlandıysanız (artık reddedilir): panelde **MCP Token** sayfasından
  bir token üretip oradaki **tek komutu** çalıştırın:
  ```
  claude mcp add --transport http abs https://<domain>/mcp --header "Authorization: Bearer abs_mcp_..."
  ```
  Bu komut `~/.claude.json`'ı **otomatik** düzenler — elle dosya açmazsınız.
  (Codex için: `codex mcp add abs --url https://<domain>/mcp --bearer-token-env-var ABS_MCP_TOKEN`.)

## Yükseltme sonrası kontrol
- [ ] `docker compose ps` — tüm servisler healthy (vault-init `exited (0)`).
- [ ] Panel → **Sağlayıcılar**: anahtarlar "Yapılandırıldı" (vault'tan yüklendi).
- [ ] Panel → **MCP Token**: token üret → `claude mcp list` → `abs ✓ Connected`.
- [ ] **Mevcut kullanıcıları denetle**: eski sürümde self-signup ile oluşan
      `role=admin` kullanıcılar varsa (yeni RBAC ile admin erişimi kazanırlar)
      Panel → Kullanıcılar'dan rollerini gözden geçirin.

## Notlar
- **Sağlayıcı anahtarları:** Her müşteri **kendi** anahtarlarını girer (panel /
  setup wizard). Ürün anahtarsız gelir.
- **Veri kaybı yok:** Mevcut `.env`'deki anahtarlar korunur; yükseltme sonrası
  panelden bir anahtarı yeniden kaydederseniz artık şifreli vault'a da yazılır.
