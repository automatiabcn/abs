# Sprint 2M — Bug Log

**Date:** 2026-05-14 (running, updated through FAZ A-M)
**Sprint:** 2M Customer E2E Audit
**Worker:** autonomous chain
**Test ortam:** lokal docker compose `/tmp/abs-customer-sim/`

---

## Müşteri perspektif manifesto

Her bug "gerçek bir Türk inşaat firması kurucusu ne hisseder" gözüyle yazılır. Teknik
açıklama + UX impact + öneri fix tek pakette.

---

## Bug tablosu

| ID | Sınıf | FAZ | Modül | Açıklama | Repro | Evidence | Öneri fix |
|----|-------|-----|-------|----------|-------|----------|-----------|
| 2M-001 | P2 | B4 | `/v1/license/status` API contract | Pre-setup halinde `Accept: application/json` header'a rağmen 307 redirect → `/setup` HTML. API client'lar JSON parse fail eder. | `curl -H "Accept: application/json" https://host/v1/license/status` → 307 instead of 503/409 JSON. | b4-smoke.txt | First-run middleware: `Accept: application/json` header'lı request'lere `503 {"error":"setup_incomplete","setup_url":"/setup"}` döndür, redirect değil. |
| 2M-002 | P2 | B3 | `infra/Caddyfile.customer` pre-DNS smoke | ACME varsayılan + `tls internal` hardcode yok. DNS olmadan ilk smoke test imkansız (Caddy TLS handshake fail). Müşteri için pre-flight blocker. | abs.sim.local DNS yok + Caddyfile default → `curl -kI https://host/` `tlsv1 alert internal error`. | b4-smoke.txt | Caddyfile'a `{$ABS_TLS_MODE:internal}` ya da `.env`'de `ABS_TLS_MODE=internal\|acme` toggle ekle. Quickstart doc'a not. |
| 2M-003 | **P0** | B4 (HTML) | setup wizard HTML i18n | "İleri" yerine **5 yerde** "Ileri" (Latin capital I U+0049, Türkçe İ U+0130 değil). Lesson 11 byte-exact ihlali. Müşteri "şirket profesyonel mi?" sorgular. | `curl -kL https://host/setup` → HTML 5x `<button>Ileri</button>` | b4-smoke.txt | `core/backend/app/setup_ui/static/index.html` veya template — `Ileri` → `İleri` global replace. Lesson 11 enforce. |
| 2M-004 | P2 | B4 (HTML) | setup wizard grammar | "Kuruluma Bitir" yerine "Kurulumu Bitir" daha doğru TR. Dative yerine accusative. | Aynı HTML | b4-smoke.txt | Aynı template — "Kuruluma Bitir" → "Kurulumu Bitir". |
| 2M-005 | P3 | B3 | compose up UX | `docker compose up -d` 60-90s alır, backend healthcheck loop'u 6×15s. Müşteri progress bar görmez, "asıldı mı?" düşünür. | `docker compose up -d` + watch | b3-compose-up.txt | Quickstart doc'a "First boot 60-90s normal, sleep 90 sonra `docker compose ps`" not. Belki `--wait` flag öner. |
| 2M-006 | P2 | C1 | setup wizard lang state | `/v1/setup/status` `"lang":"en"` döner ama `/setup` HTML Türkçe render. State-UI inconsistency. | GET `/v1/setup/status` post-reset → en, GET `/setup` HTML → tr buttons. | c-setup-wizard-6step.txt | Lang detection: Accept-Language header → state.lang sync. Default "tr" eğer client locale TR. |
| 2M-007 | P3 | C3 | brief stale (`mode:public`) | Brief FAZ C2 payload `{"mode":"public","domain":...}` örnek veriyor ama backend `Literal["ip","domain"]` bekler — 422. | POST `/v1/setup/step/domain` brief payload → 422. | c-setup-wizard-6step.txt | Brief'i güncelle: `mode:"domain"` veya `mode:"ip"`. Worker doc bug, code OK. |
| 2M-008 | P2 | C4 | setup step ping disabled | Step 4 anthropic & Step 6 test `"reason":"live ping disabled in setup"`. Format-only validation. Müşteri yanlış key paste → setup tamamlanır → ilk chat fail. | Step 4 payload `{"anthropic_api_key":"sk-ant-placeholder"}` → 200 OK. | c-setup-wizard-6step.txt | Setup Step 6 "test" gerçek 1-prompt ping yapsın (1 token, $0.0001), başarısız ise setup tamamlanmasın. Founder cost-conscious yine de minimum smoke ekle. |
| 2M-009 | **P1** | C5 | panel route mismatch | Brief `/panel/quota`, `/panel/tools`, `/panel/chat`, `/panel/meetings` rotalarını talep ediyor — gerçek hepsi 404. Canonical rota `/admin/*`. Polish memory v1.7 "/admin/* → /panel/* 308 redirect" ile çelişiyor. | `curl -kL /panel/chat` → 404; `/admin/chat` → 200. | c-admin-login-panel-route.txt | İki seçenek: (a) `/panel/* → /admin/*` redirect ekle (polish memory'yi onayla); (b) Brief'i güncelle `/admin/*`. Polish memory v1.7 yanıltıcı — invalidate veya impl ekle. |
| 2M-010 | P2 | C5 | /panel/ HTTPS downgrade redirect | `/panel/` 307 location: `http://abs.sim.local/panel` (HTTPS yerine HTTP). Cookie `SameSite=strict` ile bu cross-protocol redirect cookie drop edebilir. | `curl -kI https://host/panel/` → 307 `location: http://host/panel`. | c-admin-login-panel-route.txt | Redirect protokolü origin'den miras alsın. `https://` zorla. Backend redirect handler patch. |
| 2M-011 | P3 | E1 | MCP tool count 122 vs brief 123 | FastMCP registry `len = 122`, brief 123 hedef — 1 tool kaybı veya brief stale. STOP CRITERIA #8 trigger eşiği <80, sınırın çok üstünde — minor inconsistency. | `register_all_tools(); len(mcp_server._tool_manager._tools)` → 122 | e-mcp-rag-tr.txt | Brief'i 122'ye güncelle veya registration audit (legacy tool removed muhtemelen). |
| 2M-012 | P3 | E2 | RAG ingest brief stale (multipart) | Brief E2 `curl -F file=@... -F project_slug=...` multipart bekler. Gerçek endpoint `IngestTextRequest` JSON body alır — multipart 422. | `curl -F file=@x.md https://host/v1/rag/ingest` → 422 validation error. | e-mcp-rag-tr.txt | Brief'i JSON body örneğine güncelle. Veya `/ingest/multipart` ayrı endpoint ekle. |
| 2M-013 | P2 | E3 | MCP Streamable HTTP host validation | `/mcp/` JSON-RPC dış host header (`abs.sim.local`) ile 421 "Invalid Host header". Curl ile test imkansız. SDK clients ile OK ama smoke testing zor. | `curl https://host/mcp/ -d '{"jsonrpc":...}'` → 421 | e-mcp-rag-tr.txt | `ABS_MCP_ALLOWED_HOSTS` env'i quickstart doc'a yaz. Veya allowed_hosts'a ABS_PUBLIC_HOSTNAME otomatik eklensin. |
| 2M-014 | **P1** | F1 | MCP tool `daily_cost` IndexError | Provider-free customer-facing tool `daily_cost()` çağrıldığında `IndexError: 4` exception. Stack trace MCP client'a sızar. Müşteri "cost ne kadar?" sorusuna cevap alamaz. | `from app.mcp.server import mcp_server; mcp_server._tool_manager._tools['daily_cost'].fn()` → IndexError | f-mcp-tool-audit.txt | `daily_cost.fn` içinde guard: cost log entry yoksa `{"cost": 0, "currency":"USD","period":"today","entries":0}` döndür, IndexError yerine. |
| 2M-015 | P2 | F2 | MCP tool latency outlier `rag_status` | rag_status 423ms (vs p95 system tools <20ms). Qdrant scroll/count yaparken her seferinde tam tarama olabilir. Multi-collection durumda ölçeklemez. | `mcp_server._tool_manager._tools['rag_status'].fn()` → 422ms | f-mcp-tool-audit.txt | qdrant_client.count() cache + LRU 30s. Veya periodic background refresh. |
| 2M-016 | P3 | F2 | `news_digest` graceful degrade | Gemini API key yokken news_digest "_(query failed: Gemini API key ..._)" döner — graceful degrade ama UX'te belirsiz. | `news_digest()` no key → markdown "query failed" mesajı | f-mcp-tool-audit.txt | "News digest unavailable: Gemini API key required" gibi clear-user mesaj. |
| 2M-017 | **P0** | G3 | Cascade 6-down Türkçe fallback Lesson 11 | `/v1/chat/completions` 6-down fallback message: "Tum saglayicilar gecici hata verdi; lutfen tekrar deneyin." 8 Türkçe karakter ASCII'ye düşmüş (Ü/ü/ğ/ç/ı/ş hepsi düz). Müşteri ürün kalitesizliği hisseder. | POST `/v1/chat/completions` no provider configured → SSE event `{"content":"Tum..."}` | g-cascade-6down-audit.txt | Cascade orchestrator `_no_providers_message` literal'ı UTF-8 byte-exact'a güncelle. Test: bytes(msg.encode()) içinde `\xc4\xb0` (İ) `\xc4\xb1` (ı) `\xc5\x9f` (ş) `\xc4\x9f` (ğ) `\xc3\xa7` (ç) `\xc3\xbc` (ü). |
| 2M-018 | **P1** | G3 | Cascade 6-down HTTP 200 vs UAT-044 503 | Brief beklentisi: 503 `{"error":"providers_unavailable",...}`. Gerçek: HTTP 200 + SSE stream. Stack leak yok (UAT-044 P0 koşul OK) ama client retry semantics kaybolur — JS fetch `response.ok = true` yanıltıcı. | POST `/v1/chat/completions` 5x no-provider → 200 SSE her seferinde | g-cascade-6down-audit.txt | Stream başında `{"type":"error","code":"all_providers_unavailable","retry_after":60}` event emit + son event'te `[DONE]` öncesi HTTP 503 trailer (HTTP/2 trailers) veya alternate header `x-abs-providers-unavailable: true`. Veya başlangıçta direkt 503 ve SSE stream başlatma. |
| 2M-019 | P3 | G0 | Brief endpoint listesi stale | `/v1/chat`, `/v1/cascade/test`, `/v1/admin/cascade/breaker`, `/v1/admin/providers/circuit_state` — 4 endpoint brief'te ama gerçek 404/405. Canonical: `/v1/chat/completions`, `/v1/admin/providers/status`, `/v1/system/quota_status`. | `curl /v1/chat` → 404, `curl /v1/cascade/test` → 404, `/v1/admin/cascade/breaker` → 404 | g-cascade-6down-audit.txt | Brief'i revize: `/v1/chat/completions` SSE örneği + `/v1/admin/providers/status` + `/v1/system/quota_status`. |
| 2M-020 | P1 | H5 | Caddyfile `/me/*` route gap | Caddyfile.customer `@backend path /v1/* /auth/* /setup* /healthz /mcp* /static/* /panel /panel/* /api/inngest /api/inngest/*` — `/me/*` (eski API path) yok. Brief'in `/me/delete-request`, `/me/data-export` çağrıları landing'in Next.js 404 page'ine düşer. Silent failure, müşteri "endpoint bozuk" düşünür. | `curl https://host/me/delete-request` → 404 Next.js HTML (DEĞIL backend JSON) | h-admin-panel-kvkk-audit.txt | Caddyfile @backend pattern'a `/me/*` ekle, ya da v0 deprecation 410 Gone döndür. |
| 2M-021 | P2 | H4 | UAT-034 cap test data sparse | Audit cap=100 enforce ediliyor ama veri sadece 6 entry → 9999 limit ile de 6 döndü. Cap'i gerçek doğrulamak için 200+ entry seed gerekir. Sim ortamı seed eksik. | `?limit=9999` → 6 entry (cap=100 hedef ama veri yetersiz, fonksiyonel doğrulamadı) | h-admin-panel-kvkk-audit.txt | E2E test'e 200+ audit entry seed ekle, cap=100 kesinleştir. (Test infrastructure improvement) |
| 2M-022 | P2 | H2 | KVKK confirm_token plaintext (env dependent) | delete-request response body `confirm_token` plaintext döner — ama `settings.env != "prod"` koşulluda intended (test/dev). Customer compose default ABS_ENV unset → dev mode → plaintext sızar. Quickstart doc'a ABS_ENV=prod enforce eksik. | `curl POST /v1/me/account/delete-request` → 200 body `confirm_token` field | h-admin-panel-kvkk-audit.txt | (a) Customer compose `.env.example`'a `ABS_ENV=prod` default + comment. (b) Boot guard: `env != "prod"` ise `WARN: dev mode, do not use for real customer data`. |
| 2M-023 | **P1** | H2 | Container image `1.0.0` stale (deletion-status eksik) | `ghcr.io/enzoemir1/abs-backend:1.0.0` me_account.py 240 satır, lokal repo 355 satır. Sprint 2I UAT-038 `/v1/me/account/deletion-status` endpoint container'a deploy edilmemiş. Müşteri default `ABS_VERSION=1.0.0` kullanırsa countdown banner + scheduled_delete_at API çalışmaz. | `docker exec backend grep -c deletion-status /app/app/api/me_account.py` → 0 (lokal repo → 1+) | h-admin-panel-kvkk-audit.txt | Build + push `ghcr.io/enzoemir1/abs-backend:1.0.0-rc2` (veya 1.0.1) + `.env.example` `ABS_VERSION=1.0.0-rc2` default. CI workflow image-publish job retag. |
| 2M-024 | **P1** | I4 | `/auth/login` rate limit yok (UAT-041 regression) | 10 sequential wrong-password attempt → 10x 401, 0x 429. Brute force korumasız. UAT-041 hedef 5/min cap kaybolmuş. | 10x POST `/auth/login` `{"email":"x","password":"wrong${i}"}` → tümü 401 | i-edge-cases.txt | `slowapi` veya `fastapi-limiter` middleware `/auth/login` endpoint'ine ekle, 5 req/min per IP. Redis storage opsiyonel; in-memory yeterli small deploy. |
| 2M-025 | **P0** | I2 | UAT-009 fail-closed BROKEN (backend down → 200 panel) | `docker compose stop backend` sonrası `GET /admin/dashboard` → 200 + 34KB Next.js HTML. Landing SSR auth check yapmıyor, backend health'i probe etmiyor. Müşteri "panel çalışıyor sanır", XHR'lerle hata bulmaya çalışır. | `docker compose stop backend; curl /admin/dashboard` → 200 (beklenen 503/redirect) | i-edge-cases.txt | Landing `app/admin/layout.tsx` (veya middleware.ts) → `fetch backend /healthz` SSR'da; 5xx ise `redirect('/login')` ya da 503 page. CSP `connect-src` revize. |
| 2M-026 | **P0** | I-NEW | Customer compose Postgres yok — Sprint 2K RLS DEFENSE-IN-DEPTH AKTİF DEĞİL | `infra/docker-compose.customer.yml` Postgres service tanımlamıyor. Backend DATABASE_URL unset → SQLite fallback (`sqlite:////app/data/abs.db`). Sprint 2K Postgres RLS migration sadece dev/CI'da test edildi. Müşteri "Sprint 2K RLS güvenim var" düşünür ama gerçekte yok. | `docker exec backend python -c "from app.db.session import get_engine; print(get_engine().url)"` → sqlite | i-edge-cases.txt | Customer compose'a Postgres 16 service ekle (abs-postgres-data named volume), Sprint 2K migration default. SQLite legacy fallback `ABS_DB_BACKEND=sqlite` opt-in. Quickstart doc Postgres recipe. |

---

## P0/P1/P2/P3 sayım (FAZ I kapanışı)

- **P0 (blocker):** 4 (2M-003 setup HTML, 2M-017 cascade fallback, 2M-025 fail-closed, 2M-026 Postgres yok)
- **P1 (critical):** 6 (2M-009, 014, 018, 020, 023, 024)
- **P2 (polish):** 10 (2M-001, 002, 004, 006, 008, 010, 013, 015, 021, 022)
- **P3 (note):** 6 (2M-005, 007, 011, 012, 016, 019)

**Toplam:** 26 bulgu (FAZ A-C-E-F-G-H-I)

---

## Sprint 2N (1.0.1) — Closure Matrix

| Bug | Status | Commit / artifact |
|-----|--------|-------------------|
| 2M-003 P0 (setup HTML i18n) | ✅ Closed | fix(2n-a) — TR byte-exact blanket + CI gate (test_turkce_byte_exact_blanket.py 4/4) |
| 2M-017 P0 (cascade fallback i18n) | ✅ Closed | fix(2n-a) — chat.py 5 message byte-exact |
| 2M-025 P0 (UAT-009 fail-closed) | ✅ Closed | fix(2n-b) — admin + panel SSR /healthz probe + /login banner (vitest 8/8) |
| 2M-026 P0 (Postgres + RLS) | ✅ Closed | fix(2n-c) — postgres:16 service + entrypoint alembic gate (pytest 8/8) |
| 2M-009 P1 (panel route) | ✅ Closed | fix(2n-e) — `/panel/{path}` → `/admin/{path}` 308 catch-all |
| 2M-014 P1 (daily_cost IndexError) | ✅ Closed | fix(2n-e) — graceful fallback shape |
| 2M-018 P1 (cascade 6-down 200) | ✅ Closed | fix(2n-e) — pre-flight probe → HTTP 503 + Retry-After |
| 2M-020 P1 (Caddyfile /me/*) | ✅ Closed | fix(2n-e) — @backend pattern updated |
| 2M-023 P1 (image 1.0.0 stale) | ⚠️ Founder-gated | fix(2n-e) — .env.example 1.0.1 default; `v1.0.1` tag push founder action (Lesson 14) |
| 2M-024 P1 (rate limit) | ✅ Closed | fix(2n-e) — customer compose `ABS_RATE_LIMIT_ENABLED=true` + `ABS_ENV=prod` explicit |
| 2M-D smebes pkg incident | ✅ Closed | fix(2n-d) — scripts/build_customer_pkg.sh tek-dosya tar.gz; onboard.sh scripts/ kopyala |
| 2M-001 P2 (JSON 503 first-run) | ✅ Closed | chore(2n-f) — first_run.py Accept: application/json → JSONResponse(503) |
| 2M-002 P2 (tls toggle) | ✅ Closed | chore(2n-f) — Caddyfile.customer `# tls internal` toggle + quickstart note |
| 2M-004 P2 (Kurulumu Bitir) | ✅ Closed | fix(2n-a) — TR byte-exact blanket'a dahil |
| 2M-010 P2 (HTTPS preserve) | ✅ Closed | chore(2n-f) — uvicorn `--proxy-headers --forwarded-allow-ips=*` |
| 2M-013 P2 (ABS_MCP_ALLOWED_HOSTS doc) | ✅ Closed | chore(2n-f) — quickstart-30min.md Sprint 2N notes |
| 2M-022 P2 (ABS_ENV=prod) | ✅ Closed | fix(2n-e) — customer compose explicit default |
| 2M-005 P3 (first boot 60-90s) | ✅ Closed | chore(2n-f) — quickstart-30min.md |
| 2M-016 P3 (news_digest msg) | ✅ Closed | chore(2n-f) — _api_key_clue helper |
| 2M-007 P3 (brief domain payload) | ✅ Closed (doc) | chore(2n-f) — quickstart canonical lists |
| 2M-011 P3 (122 vs 123 MCP) | ✅ Closed (doc) | chore(2n-f) — quickstart: "122 tools (Sprint 19 retirement, well above STOP floor)" |
| 2M-012 P3 (RAG ingest body) | ✅ Closed (doc) | chore(2n-f) — quickstart JSON body example |
| 2M-019 P3 (endpoint stale) | ✅ Closed (doc) | chore(2n-f) — quickstart canonical list |
| 2M-006 P2 (lang detection) | 🟡 Deferred → Sprint 2L | Sprint 2N hot-fix scope dışı; non-blocking UX |
| 2M-008 P2 (real ping cost) | 🟡 Deferred → Sprint 2L | Founder cost-conscious karar; 1-token smoke ileri sprint |
| 2M-015 P2 (rag_status LRU) | 🟡 Deferred → Sprint 2L | Performance optimization; mevcut 423ms hâlâ <500ms |
| 2M-021 P2 (audit seed 200+) | 🟡 Deferred → Sprint 2L | Test infrastructure improvement |

**Sprint 2N exit state:** 22/26 closed (4 P0 + 6 P1 + 6 P2 + 6 P3) + 1 founder-gated (#2M-023 image push) + 4 P2 deferred to Sprint 2L (lang/ping/rag_status LRU/audit seed).

---

## Müşteri impact analizi

- **2M-003 P0** — Lesson 11 ihlali setup wizard'da. "Bu şirket Türkçe'ye gerçekten önem vermemiş" hissi. Müşteri ilk 30 saniyede güveni kaybeder.
- **2M-001 P2** — Müşteri yoksa OK; client SDK yazan partner için API contract violation. Sprint 2N hot-fix önerilir.
- **2M-002 P2** — Müşteri quickstart doc'a bakar, `tls internal` çözümünü bulamaz, ya support email atar ya pes eder.

---

**Update pattern:** FAZ C-M ilerledikçe yeni bug'lar bu tablonun altına eklenir, P0/P1/P2/P3
sayım güncellenir.

---

## Founder Recommendations — Top 5 Acil Aksiyon (FAZ L)

### 1. 🚨 Lesson 11 Türkçe karakter blanket-audit + fix (P0 #003 + #017)

İki kritik konum:
- `core/backend/app/setup_ui/static/` (veya template) — `"Ileri"` → `"İleri"` global replace, `"Kuruluma Bitir"` → `"Kurulumu Bitir"`.
- `core/backend/app/cascade/` orchestrator fallback message — `"Tum saglayicilar gecici hata verdi; lutfen tekrar deneyin."` → `"Tüm sağlayıcılar geçici hata verdi; lütfen tekrar deneyin."` byte-exact.

**Test:** Mevcut `tests/test_turkce_byte_exact.py` (varsa) + yeni assert: cascade fallback message bytes contains `\xc3\x9c` (Ü), `\xc4\x9f` (ğ), `\xc3\xa7` (ç), `\xc4\xb1` (ı), `\xc5\x9f` (ş). CI gate ekle.

**Etki:** Müşteri ilk 30 saniyede güveni iade eder. Türk pazarına satış ön-koşul.

### 2. 🚨 Postgres RLS customer compose'a entegre et (P0 #026)

Customer compose şu an Postgres servisi içermiyor → SQLite fallback. Sprint 2K defense-in-depth katmanı kaybediliyor. Çözüm:

- `infra/docker-compose.customer.yml`'a `postgres` service ekle (`postgres:16-alpine`, named volume `abs-postgres-data`).
- Backend `DATABASE_URL=postgresql+psycopg://abs:${ABS_DB_PASSWORD}@postgres:5432/abs` default.
- Setup wizard step 0'a "DB backend" toggle (Postgres default, SQLite legacy fallback).
- Migration `0000_init_baseline` + Sprint 2K RLS migration boot'ta otomatik.
- Quickstart doc'a Postgres recipe.

**Etki:** KVKK compliance defense-in-depth, cross-tenant guard 2-layer (Cerbos + Postgres RLS GUC).

### 3. 🚨 UAT-009 fail-closed restore (P0 #025)

Landing `app/admin/layout.tsx` veya `middleware.ts`:

```typescript
export async function middleware(req: Request) {
  const health = await fetch(`${process.env.ABS_BACKEND_URL}/healthz`).catch(() => null);
  if (!health || !health.ok) return Response.redirect('/login?backend_down', 307);
  // existing auth check...
}
```

**Etki:** Backend down sim → /admin/* redirect /login, müşteri "bozuk" sanmaz, fail-loud mesaj alır.

### 4. 🔴 Image `1.0.0` retag → `1.0.1` / `rc2` push (P1 #023)

`ghcr.io/enzoemir1/abs-backend:1.0.0` Sprint 2I UAT-038 (deletion-status) eksik. CI:

```yaml
# .github/workflows/image-publish.yml (varsa update)
- name: Build + push abs-backend
  run: |
    docker build -t ghcr.io/enzoemir1/abs-backend:1.0.1 .
    docker push ghcr.io/enzoemir1/abs-backend:1.0.1
```

`.env.example` `ABS_VERSION=1.0.1` default. Customer compose immediate sync.

**Etki:** Müşteri UAT-038 countdown banner + scheduled_delete_at API çalışır.

### 5. 🔴 `/auth/login` rate limit middleware (P1 #024)

`slowapi` veya `fastapi-limiter` ekle:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

@auth_router.post("/login")
@limiter.limit("5/minute")
async def login(...):
    ...
```

In-memory store yeterli (small deploy). Per-IP cap; per-email enhancement bonus.

**Etki:** Brute force korumalı, UAT-041 restore.

---

## Sprint 2N kararı (founder review için)

| Sprint | Kapsam | Süre |
|--------|--------|------|
| **Sprint 2N — Hot-fix patch (önerilir)** | 5 founder rec + 5 P1 bug fix | 1-2 hafta |
| Sprint 2L — RLS dalga 2 | tablo seti genişletme | 1 hafta (Sprint 2N sonra) |
| Pilot Batch 2 | Sprint 2N closed olmadan ❌ | gating: P0 = 0 |

**Pilot batch 2 gating kriteri:**
- ✅ Sprint 2N kapanışında **0 P0 bug** kalmalı
- ✅ P1 bug ≤ 2 (acil olmayan polish)
- ✅ Cert footer 🟡 RC → 🟢 GREEN damga
- ✅ Postgres RLS customer compose default (KVKK için zorunlu)
- ✅ Türkçe karakter blanket-audit CI gate aktif

Mevcut durumda **pilot batch 2 GO/NO-GO: NO-GO** çünkü:
- 4 P0 bug açık (#003, #017, #025, #026)
- 6 P1 bug açık (kümülatif risk)
- Cert footer 🟡 RC seviyesinde

---

## Müşteri perspektif final yorum

**Olumlu:**
- Setup time 3-8 dk EXCELLENT (hedef %10-25)
- 7/7 service docker healthy
- 122 MCP tool registered (brief 123 hedef ≈ 99%)
- KVKK 2-step + encrypted data export OK
- RAG round-trip Türkçe byte-exact PASS (storage layer)
- Cerbos + app-level RLS guard işler

**Düzeltilmeli:**
- Türkçe karakter 2 kritik konum (P0)
- Postgres RLS defense-in-depth (P0)
- Backend down → panel açık (P0)
- Image stale 1.0.0 → 1.0.1 (P1)
- Auth rate limit (P1)
- 10+ polish (P2)

**Sonuç:** Pilot 1 (mevcut 3 müşteri) gözden geçirilmeli — yeni batch açmadan önce
Sprint 2N hot-fix. Cert footer 🟡 RC; 🟢 GREEN damga Sprint 2N closed sonra eligible.

