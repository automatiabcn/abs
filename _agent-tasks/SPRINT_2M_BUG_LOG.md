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

---

## P0/P1/P2/P3 sayım (FAZ C kapanışı)

- **P0 (blocker):** 1 (2M-003 Türkçe Lesson 11 setup HTML)
- **P1 (critical):** 1 (2M-009 panel route mismatch — brief vs gerçek)
- **P2 (polish):** 6 (2M-001 API contract, 2M-002 TLS toggle, 2M-004 grammar, 2M-006 lang state, 2M-008 ping disabled, 2M-010 HTTPS downgrade)
- **P3 (note):** 2 (2M-005 first-boot UX, 2M-007 brief stale payload)

**Toplam:** 10 bulgu (FAZ A-C)

---

## Müşteri impact analizi

- **2M-003 P0** — Lesson 11 ihlali setup wizard'da. "Bu şirket Türkçe'ye gerçekten önem vermemiş" hissi. Müşteri ilk 30 saniyede güveni kaybeder.
- **2M-001 P2** — Müşteri yoksa OK; client SDK yazan partner için API contract violation. Sprint 2N hot-fix önerilir.
- **2M-002 P2** — Müşteri quickstart doc'a bakar, `tls internal` çözümünü bulamaz, ya support email atar ya pes eder.

---

**Update pattern:** FAZ C-M ilerledikçe yeni bug'lar bu tablonun altına eklenir, P0/P1/P2/P3
sayım güncellenir.
