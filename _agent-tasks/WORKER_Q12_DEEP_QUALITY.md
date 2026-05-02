# Q12 — Sürekli Kalite Döngü 3. Sweep + Yeni Boyutlar

> **Tetikleyici:** Q10 + Q11 = 16/16 layer FULL CLEAN. Sprint 21 honest verdict (bundle wins ama slow-3G regression). Founder direktifi: "kalite loop devam, sürekli üzerinden geçmeye devam edelim".
> **Hedef:** Q10/Q11 fix'lerinin **3. sweep regression** + **5 yeni layer** (L17-L21) + Sprint 21 honest results stress test.
> **Branch:** `feat/sprint-q12-deep-quality` (Sprint 21 üzerinden)
> **Worker:** Opus 4.7 (1M context) + %70+ MCP delegation

---

## 0. Ön Koşullar

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-21-perf-architecture && git pull
git checkout -b feat/sprint-q12-deep-quality

docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml ps  # backend healthy
cd core/landing && npm run build  # baseline confirm
```

**Q10/Q11/Sprint 21 baseline:**
- Backend pytest: 89 PASS
- Frontend e2e: 122+ PASS (Q10 + Q11 specs)
- 16 quality layer FULL CLEAN
- Sprint 21 bundle reduction shipped, LCP throttled regression backlogged for Sprint 22

---

## 1. Q12 LAYER MATRIX (16 inherited + 5 new = 21 layer)

### Inherited Q10/Q11 layers — 3rd sweep (regression rigour)
| # | Layer | Q10 baseline | Q11 baseline | Sprint 21 stress |
|---|-------|--------------|--------------|------------------|
| L1 | unit coverage | 32 test 3/3 | 44 test 3/3 | regression-safe |
| L2 | integration | 7 test 3/3 | enriched 3/3 | regression-safe |
| L3 | e2e theme matrix | 30 senaryo 3/3 | 60 FF+WK 3/3 | regression-safe |
| L4 | a11y axe | 15 sayfa 3/3 | 30 FF+WK 3/3 | regression-safe |
| L5 | Lighthouse perf | desktop 4/4 ≥90 | parity | **slow-3G regression — Sprint 22 backlog** |
| L6 | security | OWASP+npm 3/3 | regression-safe | regression-safe |
| L7 | visual regression | 10 baseline 3/3 | refresh 3/3 | regression-safe (Sprint 21 visual baseline güncellenmeli mi?) |
| L8 | i18n | 3/3 | 3/3 | parity |
| L9 | graceful degradation | 17/17 PASS 3/3 | parity | parity |
| L10 | stress/concurrency | (Q11 yeni) 3/3 | parity | regression |
| L11 | cross-browser | (Q11 yeni) 3/3 | parity | regression |
| L12 | responsive viewport | (Q11 yeni) 3/3 | parity | regression |
| L13 | fuzz/property | (Q11 yeni) 3/3 | parity | regression |
| L14 | data integrity | (Q11 yeni) 3/3 | parity | regression |
| L15 | API contract | (Q11 yeni) 3/3 | parity | regression |
| L16 | error UX | (Q11 yeni) 3/3 | parity | regression |

### Q12 NEW LAYERS (5 yeni boyut)
| # | Layer | Hedef | Tool/yöntem |
|---|-------|-------|-------------|
| **L17** | **bundle break-even validator** | Her code-split kararı GPT-OSS formülü ile validate edilsin: `RTT_break-even = (savedBytes / bandwidth) / numRequests`. Slow-3G (400ms RTT, 1Mbps BW) altında her dynamic-import için break-even ≥ saved-bytes-time olmalı. | Custom CI script + bundle-analyzer parse + math validator |
| **L18** | **cold-cache first-visit** | Tüm testler şu an warm-cache. İlk ziyaret cold-cache senaryosunu test et (Service Worker disable + browser cache clear). Real KOBİ pilot ilk demo açışı = cold-cache. | Playwright `context.clearCookies()` + `--disable-cache` + storage state reset |
| **L19** | **backwards compatibility** | Q9 → Q10 → Q11 → Sprint 21 fix'leri zaman içinde geri gelmiş mi? Q7 finalize gap pattern + Q8 image rebuild gap + Q9 chat session 404 + Q10 quota gate no-op + Q11 alembic migration eksik + Sprint 21 bundle code-split — hiçbiri silently regress oldu mu? | Custom regression-deep test suite — her geçmiş HIGH bug için 1 test |
| **L20** | **chaos engineering** | Random pod kill (backend container restart sırasında frontend ne görüyor?), DB disconnect (Postgres down), network partition (frontend ↔ backend 5sn drop), disk full simulation, Redis down (Sprint 21 cache layer). | docker kill --signal=9 + Toxiproxy + chaostoolkit |
| **L21** | **production deploy drill** | `git tag v1.0.0-rc1 → docker compose -f docker-compose.prod.yml up` clean install simülasyonu. Alembic upgrade head → seed admin → first login → tour. Q11-L14 finalize bayrakla — yeni deploy edenler day-one PASS olmalı. | Clean Docker volume + new compose + scripted journey |

**Q12 hedefi:** 21 layer × 3 ardışık 0-bug round = 63 round minimum FULL CLEAN. Q12-L17/L20/L21 yeni bulgu üretmesi yüksek olasılık.

---

## 2. ROUND DÖNGÜSÜ (Q10/Q11 ile aynı format)

1. Layer pick (round N % 21 rotation)
2. Real bug hunt (spec ship YETERSİZ — headless run + gerçek bulgu)
3. Fix + atomic commit (`fix(q12/L<n>): Round <N> Q12-L<n>-<seq>`)
4. Verify (regression yok — Q10/Q11/Sprint21 specs PASS)
5. Round summary (artifacts/sprint_q12/round_<N>_<layer>.md)
6. master_audit_summary.md canlı güncelle

---

## 3. Q12 BAŞLANGIÇ ROUND'LARI (öncelik sırası)

### Round 1 = L17 bundle break-even validator
GPT-OSS araştırma çıktısından formül + KOBİ network profile (slow 3G + office fiber):

```js
// scripts/validate_bundle_split.js
function rttBreakEven(savedBytes, bandwidthKbps, numRequests) {
  const bandwidthBps = (bandwidthKbps * 1000) / 8;
  const downloadSec = savedBytes / bandwidthBps;
  return (downloadSec / numRequests) * 1000; // ms
}

// Slow 3G: RTT 400ms, BW 1Mbps
// Office fiber: RTT 50ms, BW 50Mbps
// Test her dynamic-import için: break-even ≥ target_RTT olmalı
```

- Sprint 21'in 4 perf commit'ini (B/C/D) re-evaluate et
- Hangi split slow-3G'de hala mantıklı? Hangisi revert edilmeli?
- Output: artifacts/sprint_q12/round_1_L17_bundle_decisions.md
- Atomic commit: spec ship + decision matrix

### Round 2 = L21 production deploy drill (HIGH PRIORITY)
Q11-L14-001 prod-blocker (alembic 0008) düzeltildi ama **fresh prod deploy hiç test edilmedi**. KOBİ müşteri pilot için bu kritik:

```bash
# Clean volumes
docker compose down -v
docker volume prune -f

# Fresh build
docker compose -f infra/docker-compose.yml build --no-cache

# Up + alembic upgrade head + seed admin
docker compose up -d
sleep 15

# Tour: setup wizard → license → first login → all 15 pages
bash scripts/q12_l21_fresh_deploy_journey.sh

# Beklenen: 0 fail, 15/15 sayfa render, no 5xx
```

Bu Q11-L14 migration'ın gerçekten prod'da çalıştığını ZORLA garanti eder. Beklenen bulgu: 1-3 fresh-install gap (bootstrap order, env default, log path).

### Round 3 = L18 cold-cache first-visit
Playwright her test'i warm-cache çalıştırıyor. Cold-cache:
```ts
test.beforeEach(async ({ context }) => {
  await context.clearCookies();
  await context.clearPermissions();
  // browser cache clear
});
```

15 sayfa cold-cache LCP ölç → Sprint 21 honest result'la karşılaştır. Beklenen: cold-cache LCP +500ms-1s (font + initial JS download).

### Round 4 = L19 backwards compatibility deep regression
Tüm geçmiş HIGH bug için bir regression test:

| Geçmiş bug | Regression test |
|-----------|-----------------|
| Q7 finalize: graph router register | curl /v1/graph/cypher 200/401 (404 olmamalı) |
| Q8 image rebuild gap | docker exec ls /app/app/api/chat.py exists |
| Q9 chat session 404 | curl /v1/chat/sessions cookie 200 |
| Q10-L6-001 quota no-op | 200 paralel risky tool → 100 limit hit |
| Q10-L7-001 prod build break | npm run build exit 0 + meetings/[id] render |
| Q11-L13-001 chat content max | POST 16384-char content → 422 (not 500) |
| Q11-L14-001 alembic missing | alembic current shows 0008 |
| Q11-L15-001 hooks 422-before-401 | unauthenticated hook → 401 (not 422) |
| Sprint 21 chat regression | /panel/chat warm-network LCP < baseline |

### Round 5 = L20 chaos engineering — backend container kill mid-request
```bash
# Frontend kullanıcı /v1/chat/completions stream başlatır
# Backend container 5sn sonra docker kill -SIGTERM
# Frontend: connection drop görmeli, "yeniden bağlan" CTA göstermeli
```

### Round 6+ rotation:
L1 → L2 → L3 → ... → L16 → L17 → L18 → L19 → L20 → L21 → L1 (Q10 inherited deeply re-test)

---

## 4. DELEGATION ZORUNLU (%70+ MCP, Q8+Q9+Q10+Q11 ders)

- Test üretimi: `mcp__abs__write_tests` (unit, integration, e2e)
- Code review per fix: `mcp__abs__code_review tier=standard`
- Bug analiz: `mcp__abs__ask_gptoss` (root cause, break-even math)
- Fix kod: `mcp__abs__ask_kimi` veya `qual_code` pipeline
- TR error message: `mcp__abs__ask_qwen32b`
- Sec audit: `mcp__abs__qual_analysis`
- Cross-browser bug: `mcp__abs__ask_gemini_pro`
- Deploy drill: `mcp__abs__ask_kimi` (bash scripting)
- Chaos scenario: `mcp__abs__ask_gptoss` (failure mode design)
- Patch judge: `mcp__abs__judge_patch` (AST %60 + LLM %40 — yeni bulgu)

Worker (Opus/Sonnet) sadece: Read, Edit, Write, git, Playwright, dış-curl, container exec.

---

## 5. KESİN YASAK (Q7+Q8+Q9+Q10+Q11+Sprint 21 ders)

- Source ship ≠ production deploy (image rebuild backend dokunulmuşsa)
- pytest 100/100 ≠ live endpoint (dış-curl + container exec)
- Spec ship ≠ round ilerletti (headless run + gerçek bulgu)
- Bundle byte ≠ LCP (network-bound → break-even formülü)
- /schedule önerisi yapma (founder direktifi: sürekli devam)
- "Sprint 22 RSC için bekle" — Q12 bağımsız ilerler, Sprint 22 paralel başlatılır

---

## 6. ENV (founder hazır)

- Frontend dev: http://localhost:3000
- Frontend prod: cd core/landing && npm run build && npx next start -p 3458
- Backend: http://localhost:8000
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```

---

## 7. BAŞARI KRİTERİ (Q12 FULL CLEAN, hedef)

- 21/21 layer × 3 ardışık 0-bug round
- Backend pytest ≥100 (şu an 89)
- Frontend e2e ≥150 senaryo (şu an 122)
- Cold-cache LCP raporu (15 sayfa)
- Bundle break-even decision matrix (Sprint 21 her commit için)
- Fresh prod deploy 15/15 sayfa PASS (cold start)
- Backwards-compat 9/9 geçmiş HIGH regression test PASS
- Chaos engineering 5/5 senaryo (backend kill, db down, network partition, disk full, redis down)
- 0 console error tüm test senaryolarında

---

## 8. ÇIKTI

```
artifacts/sprint_q12/
├── master_audit_summary.md        (canlı layer matrix)
├── master_repro.sh                (her round entry)
├── round_<N>_<layer>.md           (per round)
├── round_1_L17_bundle_decisions.md
├── round_2_L21_fresh_deploy_journey/
├── round_3_L18_cold_cache_lcp.md
├── round_4_L19_backwards_compat/
├── round_5_L20_chaos/
└── ...
```

---

## 9. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume eder. Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 10. BAŞLANGIÇ

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-21-perf-architecture && git pull
git checkout -b feat/sprint-q12-deep-quality
mkdir -p artifacts/sprint_q12/screenshots
```

Round 1 = **L17 bundle break-even validator** (Sprint 21 commit'lerini formülle re-evaluate et). Atomic commit per finding.

Engelleyici YOK. Brief eksiksiz. Round 1'den başla.

---

## 11. PARALEL SPRINT 22 (founder bağımsız çalışır)

Q12 worker yürürken founder Sprint 22 brief'ini hazırlar:
- RSC migration roadmap (chat + tools öncelik)
- Early Hints (Link rel=preload) header config
- Big-lazy bundle consolidation (Tremor + Recharts → tek charts.bundle.js)
- Prefetch on Link enable
- Service Worker pre-cache `/panel/*` route grupları
- Edge runtime experiment (deferred — self-host Caddy zaten edge benzeri)

Worker Sprint 22'ye `_agent-tasks/WORKER_SPRINT_22_RSC.md` brief'i ile geçecek (Q12 ile paralel veya sonra).

---

**Tahmin:** Q12 ~60+ round, 4-6 session, FULL CLEAN ulaşılması ~1 hafta.
**Beklenen:** L17/L20/L21'den 5-15 yeni gerçek bulgu (özellikle fresh-deploy gap, chaos failure mode, bundle decision audit).
