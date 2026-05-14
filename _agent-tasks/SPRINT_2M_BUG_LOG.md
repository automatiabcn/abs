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

---

## P0/P1/P2/P3 sayım (FAZ H kapanışı)

- **P0 (blocker):** 2 (2M-003 setup HTML Türkçe, 2M-017 cascade fallback Türkçe)
- **P1 (critical):** 5 (2M-009 panel route, 2M-014 daily_cost, 2M-018 cascade 200, 2M-020 Caddy /me/*, 2M-023 image stale)
- **P2 (polish):** 10 (2M-001, 002, 004, 006, 008, 010, 013, 015, 021, 022)
- **P3 (note):** 6 (2M-005, 007, 011, 012, 016, 019)

**Toplam:** 23 bulgu (FAZ A-C-E-F-G-H)

---

## Müşteri impact analizi

- **2M-003 P0** — Lesson 11 ihlali setup wizard'da. "Bu şirket Türkçe'ye gerçekten önem vermemiş" hissi. Müşteri ilk 30 saniyede güveni kaybeder.
- **2M-001 P2** — Müşteri yoksa OK; client SDK yazan partner için API contract violation. Sprint 2N hot-fix önerilir.
- **2M-002 P2** — Müşteri quickstart doc'a bakar, `tls internal` çözümünü bulamaz, ya support email atar ya pes eder.

---

**Update pattern:** FAZ C-M ilerledikçe yeni bug'lar bu tablonun altına eklenir, P0/P1/P2/P3
sayım güncellenir.
