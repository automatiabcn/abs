# Q12 Session 8 — fs-scan Gap Close + Cross-Browser Deep + Sprint 22 RSC + Founder Gates

> **Tetikleyici:** Q12 Session 7 — 13 atomic round (R43-R55) shipped. Q11-L6 OWASP ZAP baseline+active **0 alert**, Q11-L13 Hypothesis **30K** + weekend cron, Q10-L4 5/5 PASS deep CLOSED, L26 R47 active drill (drop+reconnect 3/3), L18 R48 IndexedDB draft (3/3), Q12-L24-008 LOW webhook taxonomy. Backend pytest 1633 → 1665 (+32). fs-scan R52 honest ~75 gap inventory.
> **Hedef:** fs-scan honest gap close + L11 cross-browser deep (firefox + webkit) + L7 visual regression baseline drift + Sprint 22 RSC migration kickoff + L21 + Mutmut founder-gate kapanış.
> **Branch:** `feat/sprint-q12-deep-quality` (S1-S7 = 55+ commit shipped, HEAD bc0246c)

---

## 0a. ⚠️ DEV SERVER RESTART YETKİSİ (S8 dersi)

**Worker spawn ettiği dev server'ları (3457, 3458 vb.) hung olduğunda kill + restart edebilirsin. Founder onayı GEREKMİYOR.** Bu reversible operasyon.

```bash
# Hung dev server tespit:
curl -sk http://localhost:3457/ -o /dev/null -w "%{http_code}\n" -m 8
# code=000 timeout veya >30s dönüş = hung

# Restart:
lsof -i :3457 | awk 'NR>1{print $2}' | xargs kill 2>/dev/null
sleep 2
cd core/landing && nohup npx next dev --port 3457 > /tmp/next_dev_3457.log 2>&1 &
disown
# 1-3s ready bekle:
until grep -q "Ready in" /tmp/next_dev_3457.log; do sleep 1; done

# Smoke test:
curl -sk http://localhost:3457/ -o /dev/null -w "%{http_code}\n" -m 30
# 200 ise kontrol
```

Round summary'ye `dev_server_restart: 3457 reason=playwright_churn at=<timestamp>` not düş.

**İstisna:** Founder spawn ettiği port 3000 dev veya `infra-*` Docker container'lar — onlara dokunma, founder yönetir.

**3 başarısız restart sonrası** founder'a sor (root cause OS/disk/memory olabilir).

## 0. ⚠️ IMAGE REBUILD GATE (S3-S7 sürekli zafer — devam)

S7 backend round'larında image rebuild evidence yapıldı. Aynı disiplin S8'de DEVAM. Round summary'ye `image_rebuilt_at:` + `container_pytest_pass:` zorunlu.

---

## 1. ÖNCELIK — fs-scan honest gap close (HIGH)

S7 R52 raporu raw 45 / honest ~75 gap buldu. Inventory + close.

```bash
mcp__abs__fullstack_scan project_dir=/Users/eneseserkan/Main/abs-server-product format=detailed
# Output: missing modules + uncovered tests + integration gaps
```

Top 10-15 gap'i Session 8'de close et. Her biri ayrı atomic commit. fs-scan re-run round summary'ye ekle (raw → close edilen sayı).

---

## 2. L11 CROSS-BROWSER DEEP — firefox + webkit (HIGH)

S6 R42 + S7 R47/R48 hepsi **chromium-only**. Q11-L11 cross-browser tamamlanmadı. Session 8'de firefox + webkit:

```bash
cd core/landing
npx playwright test --project=firefox  __tests__/playwright/q12-l20-chaos-multi.spec.ts
npx playwright test --project=webkit   __tests__/playwright/q12-l20-chaos-multi.spec.ts
npx playwright test --project=firefox  __tests__/playwright/q12-l26-long-running.spec.ts
npx playwright test --project=webkit   __tests__/playwright/q12-l26-long-running.spec.ts
npx playwright test --project=firefox  __tests__/playwright/q10-l4-aria-live-deep.spec.ts
npx playwright test --project=webkit   __tests__/playwright/q10-l4-aria-live-deep.spec.ts
npx playwright test --project=firefox  __tests__/playwright/q12-l18-cold-cache.spec.ts
npx playwright test --project=webkit   __tests__/playwright/q12-l18-cold-cache.spec.ts
```

Her test çapında 4 browser PASS (chromium + firefox + webkit + chromium-mobile) zorunlu. Browser-spesifik fail varsa fix.

---

## 3. SPRINT 22 RSC MIGRATION KICKOFF (HIGH)

Sprint 21'de bundle byte reduction yaptık ama slow 3G LCP +1230ms regress yaşadık. RSC (React Server Components) migration deferred edilmişti — Session 8'de kickoff:

### Phase A: Audit
```bash
# Q12-L17 break-even validator output'unu RSC kararı için kullan
node core/landing/scripts/bundle_analysis.js
# Hangi route'lar RSC adayı (heavy server data + low interactivity)?
# Aday: /panel/dashboard, /admin/audit, /admin/users, /pricing, /privacy, /terms
```

### Phase B: 1-2 route RSC migrate
- `/admin/audit` → server component (just data fetch + render, no interactivity)
- `/admin/users` → server component

### Phase C: Lighthouse re-baseline
- LCP slow 3G: target -800ms (Sprint 21 +1230ms regress'i kapatma)
- Total bundle: target -10% from chat-heavy `/panel/chat`

---

## 4. L7 VISUAL REGRESSION BASELINE DRIFT (MEDIUM)

S6+S7'de panel UI değişiklikleri shipped (R35 ChatErrorTile, R48 SW status indicator). Visual baseline drift olmuş olabilir.

```bash
cd core/landing
npx playwright test __tests__/playwright/q10-l7-visual-regression.spec.ts --update-snapshots
# Diff'leri review, intentional değişiklikleri commit, regresyon olanları fix
```

Drift bulgu inventory + intentional vs regression ayrımı.

---

## 5. L8 I18N LOCALE PARITY DEEP (MEDIUM)

`__tests__/locale-parity.test.ts` mevcut. S8'de:
- Yeni eklenen string'ler (R35 sessions-error-tile, R48 SW status, ZAP fix) TR + EN + ES'te var mı?
- Pluralization rules (1 mesaj / 5 mesaj / 1000 mesaj) doğru mu?
- Date format locale-aware mı (TR DD.MM.YYYY vs EN MM/DD/YYYY vs ES DD/MM/YYYY)?
- Number format (TR 1.234,56 vs EN 1,234.56 vs ES 1.234,56)?

---

## 6. FOUNDER APPROVAL GATE — L21 + MUTMUT (LOW)

S5+S6+S7'de SKIP. S8'de yine SKIP veya founder onaylarsa actual:

### L21 destructive ACTUAL
```bash
ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash scripts/chaos/destructive_drill.sh
```

### Mutmut local actual (1 module)
```bash
ABS_MUTATION_RUN=1 cd core/backend && ./.venv/bin/mutmut run \
  --paths-to-mutate=app/auth/oauth/server.py --tests-dir=tests/
```

**Founder onay olmadan çalıştırma.** Yoksa SKIP commit.

---

## 7. ROUND DÖNGÜSÜ

1. Layer pick (öncelik: fs-scan gaps → cross-browser firefox/webkit → RSC kickoff → visual baseline → i18n parity)
2. Real bug hunt (spec ship YETERSİZ)
3. **Image rebuild + container exec** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** + **dış-curl smoke**
6. Round summary `artifacts/sprint_q12/round_<N>_<focus>.md` veya `artifacts/sprint_22/round_<N>_<focus>.md`
7. master_audit_summary.md canlı güncelle

---

## 8. BAŞLANGIÇ ROUND'LARI

### Round 56 = fs-scan honest gap inventory + close ilk 5
mcp__abs__fullstack_scan + top 5 gap close per atomic commit.

### Round 57 = L11 cross-browser firefox — chaos + long-running + a11y + cold-cache
4 spec firefox project. Browser-spesifik fail fix.

### Round 58 = L11 cross-browser webkit — aynı 4 spec
WebKit özellikle SSE + IndexedDB davranışı farklı olabilir.

### Round 59 = Sprint 22 RSC Phase A — audit + decision
Bundle analysis + 2 aday route belirle (`/admin/audit` + `/admin/users`).

### Round 60 = Sprint 22 RSC Phase B — /admin/audit migrate
Server component conversion + Lighthouse before/after.

### Round 61 = Sprint 22 RSC Phase B — /admin/users migrate

### Round 62 = L7 visual regression baseline drift refresh

### Round 63 = L8 i18n locale parity deep audit (yeni string'ler + format)

### Round 64+ = fs-scan kalan gap close

### (Founder approval) = L21 ACTUAL + Mutmut local

---

## 9. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- fs-scan: `mcp__abs__fullstack_scan` + `mcp__abs__fullstack_plan`
- RSC patterns: `mcp__abs__ask_kimi` (React Server Components + Next 15)
- Cross-browser issues: `mcp__abs__ask_gptoss` (browser engine differences)
- Visual diff analysis: `mcp__abs__qual_analysis`
- i18n locale: `mcp__abs__ask_qwen32b`
- Patch judge: `mcp__abs__judge_patch`

---

## 10. KESİN YASAK

- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- Selective subset ≠ FULL CLEAN
- Spec ship ≠ runtime interception (S6 dersi)
- L21 + Mutmut actual = founder approval ZORUNLU
- Pilot/market/outreach gündem dışı
- RSC migration breakdown: Lighthouse before/after gerekli, regresyon = revert

---

## 11. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3000 (canlı)
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s8_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```
- Playwright firefox + webkit: `npx playwright install firefox webkit` (ilk run önce)

---

## 12. BAŞARI KRİTERİ (Session 8 hedefi)

- fs-scan honest 75 gap → en az 15 close
- L11 cross-browser firefox + webkit 8 spec PASS (mevcut chromium spec'ler)
- Sprint 22 RSC Phase A audit + Phase B 2 route migrate + Lighthouse +800ms LCP iyileştirme
- L7 visual regression baseline drift inventory
- L8 i18n locale parity yeni string + format coverage
- Backend pytest ≥1690 (şu an 1665, hedef +25)
- 5+ yeni real bug (özellikle cross-browser + RSC migration'dan beklenir)
- Image rebuild gate her backend round

---

## 13. PRIORITY (Session 8 odak)

**HIGH:**
1. fs-scan honest gap inventory + ilk 15 close
2. L11 cross-browser firefox + webkit deep (S6+S7 chromium-only)
3. Sprint 22 RSC migration kickoff (S21 deferred RSC)

**MEDIUM:**
4. L7 visual regression baseline drift refresh
5. L8 i18n locale parity deep (yeni string + format)

**LOW (founder approval):**
6. L21 destructive ACTUAL drill
7. Mutmut local actual run

---

## 14. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 9.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 15. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -55
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_8.md
```

Round 56 = fs-scan honest gap inventory + close ilk 5'ten başla. Atomic commit per round.
Image rebuild + container exec evidence ZORUNLU.

Engelleyici YOK. Brief eksiksiz.
