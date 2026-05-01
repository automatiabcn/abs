# Automatia ABS — Mimari

Bu belge, ABS'nin teknik mimarisini tanımlar: bileşenler, veri akışı, güvenlik, çalışma akışı, teknoloji seçimleri ve ölçekleme planı.

## 1. Genel Mimari Diyagramı

```
┌──────────────── Müşteri Linux Sunucusu (Docker Compose) ────────────────┐
│                                                                          │
│  Caddy (reverse proxy + Let's Encrypt otomatik SSL)                      │
│   ├─ /                    → Landing redirect (varsa)                     │
│   ├─ /login               → Basit admin auth (lisans key'li)             │
│   ├─ /panel               → Mevcut HTML panel (D hibrit, 7550 satır)     │
│   ├─ /admin               → Next.js micro-app (opsiyonel)                │
│   ├─ /api                 → Python orchestration backend                 │
│   ├─ /stream              → SSE (5 event type: metrics, orch, cohere,    │
│   │                         mcp-tools, quota-status)                     │
│   └─ /mcp                 → MCP endpoint (Claude Code bağlanır)          │
│                                                                          │
│  ABS Orchestrator (Python backend)                                       │
│   ├─ 75 MCP tool (abs_mcp_server port)                                   │
│   ├─ 5 hook modülü (feature_nudge, delegate_nudge, plan_first,           │
│   │  rag_inject, enrichment)                                             │
│   ├─ 13 quality pipeline (qual-code, qual-tr, qual-analysis, ...)        │
│   ├─ Senior Judge (AST %60 + LLM %40)                                    │
│   ├─ Workflow durability (SQLite checkpoint)                             │
│   ├─ Symbol-aware RAG (10K sembol + 13K callsite)                        │
│   ├─ Cache hit counter                                                   │
│   └─ Cohere threshold alert                                              │
│                                                                          │
│  SQLite DB (MVP, single-user)                                            │
│  age/sops encrypted secrets volume (API key'ler)                         │
│  Ollama container (opsiyonel, yerel LLM fallback)                        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
            │
            ├─── Geliştirici CLI (Claude Code) ── local machine
            │    `claude mcp add abs https://abs.domain.com/mcp`
            │
            └─── Web tarayıcı (panel) ── her cihaz
                 https://abs.domain.com/panel
```

## 2. Bileşen Detayları

| Bileşen | Ne yapar | Kaynak |
|---|---|---|
| Caddy | Reverse proxy, otomatik HTTPS (Let's Encrypt), forward_auth | Upstream |
| Python Orchestrator | Asıl iş mantığı (MCP + hook + pipeline + cascade + judge + RAG) | SERVER port |
| SQLite DB | Workflow state + judge log + cache metadata + audit | Native |
| age/sops | Encrypted secrets at rest (API key, lisans key) | Native |
| Ollama | Yerel LLM fallback, opsiyonel (GPU varsa performanslı) | Upstream |
| Mevcut panel HTML | 7550 satır D hibrit, auth proxy arkasına alınır | SERVER port |
| Next.js admin | Opsiyonel mikro-app — lisans yönetim, provider config UI | Yeni |

## 3. Erişim ve Endpoint Tablosu

| URL | Kim erişir | Amaç |
|---|---|---|
| `https://abs.domain.com/panel` | Admin (login sonrası) | Dashboard, cosmos, widget'lar |
| `https://abs.domain.com/admin` | Admin | Lisans, provider, ayar |
| `https://abs.domain.com/api/*` | İçeriden (panel, CLI) | REST API |
| `https://abs.domain.com/stream` | İçeriden (panel) | SSE real-time events |
| `https://abs.domain.com/mcp` | Claude Code, custom CLI | MCP endpoint |
| `https://abs.domain.com:443` | Caddy tüm trafik | Otomatik SSL |

## 4. Provider Cascade — 7 Katmanlı Koruma

```
1. Abstraction Layer
   Müşteri kodu: model="fast-reasoning"
   ABS config: model_alias_map → provider + model_id
   (Provider değişince JSON güncellenir, kod dokunulmaz)
         ↓
2. Circuit Breaker
   5 hata / 1dk → "open" state (60s)
   Half-open: test → full recovery veya tekrar open
         ↓
3. Cascade Fallback
   Groq → Cerebras → CloudFlare → Gemini → Anthropic
   (müşteri config'ten sıra ayarlanır)
         ↓
4. Semantic Cache (SHA-256 prompt hash, 5dk TTL)
   Provider yavaş/down → cache'ten dön
         ↓
5. Health Monitor (müşteri sunucusunda, 60s ping)
   Status panel'de anlık: yeşil/sarı/kırmızı
         ↓
6. Central Watchdog (bizim tarafta, günde 1)
   Provider pricing + changelog + status + synthetic test
         ↓
7. Update Channel (release-based)
   provider_configs/*.yaml güncellemesi release'e dahil
```

Detay: `docs/operations.md` § 2-5.

## 5. Güvenlik Katmanı

| Katman | Mekanizma |
|---|---|
| **API key storage** | age/sops encrypted at rest. Memory'de clear text tutulmaz |
| **Transport** | Caddy + Let's Encrypt otomatik HTTPS |
| **Auth** | Admin login (lisans key'li, JWT session) |
| **Audit log** | Kim ne zaman hangi key'i ekledi/değiştirdi |
| **Data residency** | Müşteri kodu ABS sunucusunda kalır; provider API'ye gider (müşteri kendi hesabıyla) |
| **Lisans doğrulama** | JWT RS256 imza, phone-home yok, offline çalışır |
| **Secret rotation** | Panel'den tek tık |

**Önemli:** ABS bulut sunucumuza **hiçbir müşteri verisi gelmez**. Sadece lisans key doğrulama sinyali (hash-based) bizim watchdog'a ulaşır. Prompt'lar ve kod doğrudan müşteri sunucusundan provider API'lerine gider.

## 6. Müşteri Çalışma Akışı

**Kurulum:**
1. Müşteri Linux sunucu kiralar (Hetzner, DO, AWS vb.)
2. `curl -fsSL https://get.abs.automatiabcn.com/install.sh | bash`
3. Docker + Docker Compose + ABS container'ları kurulur (~5 dk)
4. Browser'da `https://sunucu-ip:8443/setup` açılır
5. 6 adım wizard (admin + lisans + domain/IP + Anthropic key + opsiyonel provider + test)

**Günlük kullanım:**
1. Geliştirici kendi makinesinde `claude mcp add abs https://abs.company.com/mcp`
2. Terminal'de `claude` açar
3. Prompt gönderir → Claude Code MCP üzerinden ABS'ye iletir
4. ABS **abstraction layer** → **circuit breaker** → **cascade** → provider
5. Yanıt geri döner, ABS'den Claude Code'a
6. Panel'de log + metrics + widget güncellenir

**Monitoring:**
1. Admin panel'den provider status izler
2. Audit log görünür
3. Budget tracker (Anthropic API kullanımı)
4. Judge skorları, workflow durumları

## 7. Teknoloji Stack

| Katman | Teknoloji | Neden |
|---|---|---|
| Reverse proxy | **Caddy** | Otomatik HTTPS, basit Caddyfile |
| Backend | **Python 3.11+** | SERVER ile aynı, port kolay |
| Database | **SQLite (MVP)** → **PostgreSQL (Faz 2+)** | Single-user basit, multi-tenant sonra |
| Auth | **Lucia** (MVP) → **Authentik** (Faz 2+) | MVP single-user, growth multi-user |
| Admin UI | **Vanilla JS + Alpine.js** veya **SvelteKit** (Next.js ek) | Hafif, mevcut panel stili uyumlu |
| Secrets | **age** + **sops** | Modern, basit, offline |
| Container | **Docker Compose** | Tek dosya, dev/prod aynı |
| LLM fallback | **Ollama** (Linux, Apple Silicon MLX yerine) | Cross-platform |

## 8. Ölçekleme Yaklaşımı (MVP → Growth)

### MVP (Ay 1-3): Single-User Self-Host
- 1 kurulum = 1 kullanıcı
- SQLite + Lucia + tek admin
- Docker Compose tek dosya
- Müşteri sayısı: 5-20
- Tavan: kullanıcı başına 1 sunucu

### Growth (Ay 3-6): Managed Cloud Beta
- 3-5 beta müşteri bizim sunucumuzda
- PostgreSQL schema-per-tenant
- Basit admin dashboard (bizim tarafta)
- Automatic backup + monitoring
- $79/ay fiyat (beta)

### Scale (Ay 6-12): Managed Cloud Full
- 20+ müşteri
- PostgreSQL RLS (row-level security)
- Authentik multi-tenant
- Kubernetes değil (overkill solo için) — VPS + Caddy + Docker
- Uptime %99.5+ SLA

### Enterprise (Yıl 2+): VPC / On-Prem Dedicated
- Müşteri kendi VPC'sinde dedicated ABS instance
- Automatia managed (opsiyonel)
- SOC 2 Type II hazırlığı
- Custom SLA

---

Uygulama detayları `_agent-tasks/` altında task bazlı yazılacak.
