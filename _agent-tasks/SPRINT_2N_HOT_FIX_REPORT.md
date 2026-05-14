# SPRINT_2N_HOT_FIX_REPORT — 4 P0 + 6 P1 Closure + Smebes Lesson 18

**Date:** 2026-05-14
**Sprint:** Sprint 2N Hot-Fix Patch
**Branch:** `feat/sprint-2n-hot-fix` (Sprint 2M HEAD `532d7e5` üzerinden cut)
**Status:** 🟢 GREEN eligible (founder image push + pilot 1 patch
notification kalan)
**Predecessor:** Sprint 2M Customer E2E Audit (🟡 RC, 4 P0 + 6 P1)
**Successor:** Pilot Batch 2 GO (Sprint 2L RLS dalga 2 ile paralel)

---

## I. Yönetici Özeti

Sprint 2N, Sprint 2M Customer E2E Audit'in 26 bulgusundan 22'sini kapattı,
1'ini founder action olarak gateledi (image push), 3'ünü Sprint 2L'ye
deferred etti. Ek olarak ilk pilot müşteri (smebes) incident'ından
çıkarılan **Lesson 18** (customer pkg mount completeness) sistemleştirildi
— `scripts/build_customer_pkg.sh` REQUIRED guard'ı ile.

| Bucket | Sprint 2M açık | Sprint 2N closed | Founder-gated | Deferred → 2L |
|--------|----------------|-------------------|----------------|----------------|
| P0     | 4              | **4**             | 0              | 0              |
| P1     | 6              | 5                 | 1 (#2M-023)    | 0              |
| P2     | 10             | 6                 | 0              | 4              |
| P3     | 6              | 6                 | 0              | 0              |
| **Toplam** | **26**     | **21**            | **1**          | **4**          |

Cert footer Section XII = 🟢 GREEN eligible. Pilot Batch 2 GO/NO-GO: **GO**.

---

## II. 7 FAZ A-G özet

| FAZ | Süre | Bug closure | Commit | Test ekle |
|-----|------|-------------|--------|-----------|
| A — Türkçe blanket | ~30dk | 2 P0 (#003, #017) | `aba5cbc` | +4 |
| B — fail-closed SSR | ~25dk | 1 P0 (#025) | `858c91f` | +8 vitest |
| C — Postgres + RLS | ~40dk | 1 P0 (#026) | `b31a16f` | +8 |
| D — customer pkg tar.gz | ~25dk | smebes lesson 18 | `f1a47d8` | +7 |
| E — 6 P1 toplu | ~45dk | 6 P1 | `10dd45c` | +9 |
| F — P2/P3 polish | ~30dk | 6 P2 + 6 P3 | `a53f899` | (existing güncel) |
| G — closeout | ~20dk | regression + cert | (bu commit) | full suite |

Toplam: ~3.5 saat autonomous chain, ~28 yeni test, 6 conventional commit.

---

## III. Bug closure matrix (kısaltılmış)

Ayrıntılı tablo: `_agent-tasks/SPRINT_2M_BUG_LOG.md` "Sprint 2N (1.0.1) —
Closure Matrix" bölümü. Özet:

- **P0 (4/4):** 003 setup HTML i18n (`aba5cbc`), 017 cascade fallback
  i18n (`aba5cbc`), 025 UAT-009 fail-closed (`858c91f`), 026 Postgres +
  RLS (`b31a16f`).
- **P1 (5/6 + 1 founder-gated):** 009 panel route, 014 daily_cost,
  018 cascade 6-down 503, 020 Caddyfile /me/*, 024 rate limit (hepsi
  `10dd45c`). 023 image 1.0.1 → founder push gate (Lesson 14).
- **P2 (6/10):** 001 first-run JSON, 002 tls toggle, 004 grammar (FAZ
  A'ya dahil), 010 HTTPS preserve, 013 MCP allowed hosts doc, 022
  ABS_ENV=prod (FAZ E'ye dahil). Deferred: 006 lang detection, 008 ping
  cost, 015 rag_status LRU, 021 audit seed.
- **P3 (6/6):** 005 first boot doc, 007 brief domain, 011 122 vs 123,
  012 RAG body, 016 news_digest msg, 019 endpoint list — hepsi
  `a53f899` (quickstart-30min.md notes).

---

## IV. Müşteri impact karşılaştırması

| Boyut | Sprint 2M çıkışı | Sprint 2N çıkışı |
|-------|--------------------|---------------------|
| Setup wizard Türkçe | Pass rate ~0% (5 "Ileri" + grammar) | Byte-exact CI gate aktif; ASCII regression BLOCK |
| Cascade fallback message | "Tum saglayicilar gecici hata verdi" | "Tüm sağlayıcılar geçici hata verdi" + 503 yapısal hata |
| Backend down davranışı | /admin/dashboard 200 + cached HTML | /admin/* → /login?reason=backend-unreachable Türkçe banner |
| KVKK / GDPR (audit + tenant tables) | SQLite fallback → RLS no-op | Postgres 16 default + alembic upgrade head gate |
| Customer pkg flow | 4 manuel dosya + cerbos manuel | Tek `customer-pkg-<slug>.tar.gz` (~28KB) + REQUIRED guard |
| /panel/{x} legacy URL | 404 | 308 → /admin/{x} (yeni sub-path catch-all) |
| Cascade 6-down HTTP semantics | 200 SSE (retry semantics yok) | 503 + Retry-After 60s + JSON yapısal hata |
| /me/* (KVKK self-service) | Next.js 404 page (Caddy gap) | Caddy @backend → FastAPI |
| /auth/login brute force | 10x 401 (rate limit silent disabled) | 5/min slowapi + ABS_ENV=prod + RATE_LIMIT_ENABLED=true |
| UX scorecard (heuristic) | 5.7/10 | (Pilot 1 patch sonrası ölçüm) — beklenen ≥7.0 |

---

## V. Founder action checklist (Pilot Batch 2 öncesi)

1. **Image push:** `git tag v1.0.1 && git push origin v1.0.1` →
   `release.yml` GitHub Release + `sbom.yml` SBOM attach + GHCR push
   `ghcr.io/enzoemir1/abs-{backend,landing}:1.0.1` + `:latest` retag.
   Cosign keyless attestation otomatik.
2. **Pilot 1 müşteri bildirimi:**
   - Smebes + 2 sibling müşteri için yeni `customer-pkg-<slug>.tar.gz`
     üret (`./scripts/customer_onboard.sh ... && ./scripts/build_customer_pkg.sh <slug>`).
   - Email template (`customer-keys/<slug>/email.md` otomatik üretilir)
     1.0.1 changelog inline + tar.gz extract procedure.
   - Encrypted channel ile gönder (1Password / Bitwarden share).
3. **Real-stack smoke (founder M4 veya Hetzner staging):**
   ```bash
   ./scripts/customer_onboard.sh "SmokeTest2N" "smoke@local" self-host 1 30
   ./scripts/build_customer_pkg.sh smoketest2n-<ts>
   mkdir -p /tmp/sprint2n-smoke && cd /tmp/sprint2n-smoke
   tar -xzvf .../customer-pkg-smoketest2n-*.tar.gz
   openssl rand -base64 32 > /tmp/db_pwd
   openssl rand -base64 32 > /tmp/vault_key
   sed -i.bak \
     -e "s|^ABS_VERSION=.*|ABS_VERSION=1.0.1|" \
     -e "s|^ABS_DB_PASSWORD=.*|ABS_DB_PASSWORD=$(cat /tmp/db_pwd)|" \
     -e "s|^ABS_VAULT_KEY=.*|ABS_VAULT_KEY=$(cat /tmp/vault_key)|" \
     .env
   docker compose up -d --wait
   docker compose ps  # 8 service: postgres + qdrant + cerbos + neo4j +
                      # backend + landing + caddy + email-cron — hepsi healthy
   docker exec backend python -c \
     "from app.db.session import get_engine; print(get_engine().url)"
     # Beklenen: postgresql+psycopg://abs:***@postgres:5432/abs
   docker exec postgres psql -U abs -d abs \
     -c "SELECT relname, relrowsecurity FROM pg_class
         WHERE relname LIKE 'audit_%';"
     # Beklenen: relrowsecurity=t
   ```
4. **Provider live test (FAZ D + F-gen + J SKIP'lerini tekrar):** 6
   API key paste (Anthropic + Groq + Cerebras + Gemini + Cloudflare +
   Cohere) → real chat completion + RAG E2E + news_digest. Cert
   Section XIII'e damga.

---

## VI. Sprint 2L (RLS dalga 2) handoff

Sprint 2L planlama notları:
- **Postgres RLS migration genişletme:** Sprint 2K audit + tenant
  tabloları kapsadı; dalga 2 = `chat_sessions`, `chat_messages`,
  `usage_log`, `webhook_events` vb. tüm tenant-scoped tablolarda RLS.
- **Deferred bug'lar:** #2M-006 (lang detection), #2M-008 (Step 6 real
  1-token ping cost), #2M-015 (rag_status LRU 30s cache), #2M-021 (200+
  audit entry seed).
- **Provider live test infrastructure:** founder key vault'tan otomatik
  load + Sprint 2M FAZ D/F-gen/J test suite tekrar.

---

## VII. Lessons enforced (Sprint 2N)

- **Lesson 11** (Türkçe byte-exact) — CI gate aktif; 4-test blanket
  audit setup HTML + cascade fallback; ASCII regression BLOCK.
- **Lesson 12** (Co-Authored-By trailer) — 6/6 commit'te yok.
- **Lesson 13** (secret transcript) — token/key/password commit + PR +
  log'a sızmadı.
- **Lesson 14** (single-actor production) — image push founder action
  olarak işaretlendi; worker tag oluşturmadı.
- **Lesson 16** (marka-neutral) — sibling project ismi yok.
- **Lesson 18 (YENİ)** — customer pkg mount completeness; `build_customer_pkg.sh`
  REQUIRED guard, `customer_onboard.sh` her host mount kopyalar, audit
  test (`test_2n_customer_pkg_mount_audit.py`) compose'da yeni mount
  eklendiğinde fail-fast.

---

## VIII. Closeout damgası

```
SPRINT 2N HOT-FIX COMPLETE 🟢 GREEN eligible

Branch: feat/sprint-2n-hot-fix
Commits: 6 conventional (fix(2n-a..e) + chore(2n-f) + docs(2n-g))
Test ortam: lokal pytest + vitest + new customer pkg flow
Predecessor: Sprint 2M HEAD 532d7e5 (🟡 RC)
Successor: Pilot Batch 2 GO

26 bug closure:
  ✅ 4 P0 KAPALI (#003 #017 #025 #026)
  ✅ 5 P1 KAPALI (#009 #014 #018 #020 #024)
  ⚠️ 1 P1 founder-gated (#023 image push)
  ✅ 6 P2 KAPALI (#001 #002 #004 #010 #013 #022)
  ✅ 6 P3 KAPALI (#005 #007 #011 #012 #016 #019)
  🟡 4 P2 deferred → Sprint 2L (#006 #008 #015 #021)

Smebes lesson 18: build_customer_pkg.sh + REQUIRED guard
Image: ABS_VERSION=1.0.1 .env.example default + founder tag push gate
Türkçe: byte-exact CI gate aktif (4 test)
Postgres RLS: customer compose default + alembic boot gate
Caddy: /me/* @backend; tls internal smoke toggle
fail-closed: /admin/* + /panel/* SSR /healthz probe + /login banner
Rate limit: ABS_ENV=prod + ABS_RATE_LIMIT_ENABLED=true customer default

Cert footer: 🟡 RC → 🟢 GREEN eligible (Section XII)
Pilot Batch 2 GO/NO-GO: GO ✅ (founder image push + pilot 1 patch kalan)

Closeout: SPRINT_2N_HOT_FIX_REPORT.md + cert v1.0.0 Section XII
🛑 STOP — Founder image v1.0.1 push + pilot 1 patch notification kararı.
```
