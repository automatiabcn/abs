# Q12 Session 9 — PRODUCTION READINESS VALIDATION (Test Bitiriliyor)

> **Founder direktifi (2026-05-04):** "artik gercekten sistemin hazir oldugundan emin olmaliyiz test asamalarini yavas yavas bitirecegiz"
>
> **Tetikleyici:** Q12 S1-S8 = 75 atomic round shipped. 10/10 Q12 layer FULL CLEAN ⭐, Q11-L6 ZAP 0 alert, Q10-L4 deep CLOSED, RSC 3 route + SSR contract 28 test, backend pytest 1718. Sistem teknik olarak olgun.
> **Hedef değişiyor:** Yeni test layer EKLEMEYECEĞİZ. Mevcut sistemi END-TO-END production readiness olarak DOĞRULAYACAĞIZ. Tester teslimat eşiğine yaklaşıyoruz.
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD ba22cd1)

---

## 0a. ⚠️ DEV SERVER RESTART YETKİSİ (S8 dersi — devam)

Worker spawn ettiği dev server (3457) hung olunca kill+restart yetkilisin. Founder onayı GEREKMİYOR. Reversible.

```bash
curl -sk http://localhost:3457/ -m 8 -o /dev/null -w "%{http_code}\n"
# 000 timeout → restart:
lsof -i :3457 | awk 'NR>1{print $2}' | xargs kill 2>/dev/null
sleep 2 && cd core/landing && nohup npx next dev --port 3457 > /tmp/next_dev_3457.log 2>&1 & disown
until grep -q "Ready in" /tmp/next_dev_3457.log; do sleep 1; done
```

---

## 0. ⚠️ IMAGE REBUILD GATE (S3-S8 sürekli — devam)

Backend dokunulduysa image rebuild + container exec evidence ZORUNLU.

---

## 1. ÖDEV — PRODUCTION READINESS VALIDATION (TEK ODAK)

Bu session'da **yeni test yazmıyoruz**. Mevcut sistemi tester teslimat seviyesinde doğruluyoruz. Memory: `project_tester_handoff_plan.md`.

### 1.1 SETUP WIZARD E2E FULL SWEEP (11 step Playwright — EN ÖNEMLİ)
Tester'ın ilk teması = setup wizard. Tek spec, fresh state'ten landing'e:

```ts
// __tests__/playwright/production_readiness_setup_wizard.spec.ts
test('E2E setup wizard full sweep: fresh deploy → first message', async ({ page }) => {
  test.slow();
  test.setTimeout(15 * 60 * 1000);  // 15 dk

  // 0. Fresh state (assumes isolated namespace or pre-seeded clean DB)
  await page.goto('http://localhost:3000/setup');

  // Step 1: admin email + password
  await page.fill('[data-testid="admin-email"]', 'tester@example.com');
  await page.fill('[data-testid="admin-password"]', 'TesterPass2026!');
  await page.click('[data-testid="step-next"]');

  // Step 2: license activation key
  await page.fill('[data-testid="license-key"]', process.env.ABS_TEST_LICENSE_KEY!);
  await page.click('[data-testid="step-next"]');

  // Step 3: domain
  await page.fill('[data-testid="domain"]', 'localhost');
  await page.click('[data-testid="step-next"]');

  // Step 4: Anthropic key (skip — provider degradation test)
  await page.click('[data-testid="step-skip"]');

  // Step 5: Free providers (Groq + Gemini + Cerebras + Cohere + Cloudflare)
  for (const p of ['groq', 'gemini', 'cerebras', 'cohere', 'cloudflare']) {
    const key = process.env[`ABS_TEST_${p.toUpperCase()}_KEY`];
    if (key) await page.fill(`[data-testid="${p}-key"]`, key);
  }
  await page.click('[data-testid="step-next"]');

  // Step 6: Test ping each provider
  await page.click('[data-testid="test-ping-all"]');
  await page.waitForSelector('[data-testid="ping-result"]', { timeout: 60000 });
  // Expected: 5/5 PASS or graceful degradation per missing key
  await page.click('[data-testid="step-finalize"]');

  // Login → /panel
  await page.fill('[data-testid="login-email"]', 'tester@example.com');
  await page.fill('[data-testid="login-password"]', 'TesterPass2026!');
  await page.click('[data-testid="login-submit"]');
  await page.waitForURL(/\/panel/, { timeout: 30000 });

  // First chat (cascade routing)
  await page.goto('http://localhost:3000/panel/chat');
  await page.fill('[data-testid="chat-input"]', 'Merhaba, sistem hazır mı?');
  await page.click('[data-testid="chat-send"]');
  await page.waitForSelector('[data-testid="chat-response"]', { timeout: 30000 });

  // First RAG ingest + query
  await page.goto('http://localhost:3000/admin/rag');
  await page.fill('[data-testid="rag-text"]', 'ABS test dokümanı, version 1.0.0.');
  await page.click('[data-testid="rag-ingest"]');
  await page.waitForSelector('[data-testid="rag-ingested"]', { timeout: 30000 });
  await page.fill('[data-testid="rag-query"]', 'ABS version nedir?');
  await page.click('[data-testid="rag-search"]');
  await page.waitForSelector('[data-testid="rag-result"]', { timeout: 30000 });

  // First workflow synthesize + dry-run + execute
  await page.goto('http://localhost:3000/admin/workflow-builder');
  await page.fill('[data-testid="wf-prompt"]', 'Bir e-posta geldiğinde Slack DM gönder.');
  await page.click('[data-testid="wf-synthesize"]');
  await page.waitForSelector('[data-testid="wf-graph"]', { timeout: 60000 });
  await page.click('[data-testid="wf-dry-run"]');
  await page.waitForSelector('[data-testid="wf-dry-result"]', { timeout: 30000 });
});
```

11 step PASS = tester gerçek müşteri yolculuğunu yaşıyor demek. Bu spec FAIL olursa **production-ready DEĞİL**.

### 1.2 PROVIDER DEGRADATION MATRIX (0-6 missing key)
Memory: `feedback_provider_degradation_test.md`. 7 senaryo:

| Senaryo | Anthropic | Groq | Gemini | Cerebras | Cohere | Cloudflare | Beklenen |
|---------|-----------|------|--------|----------|--------|------------|----------|
| All present | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 6/6 cascade aktif |
| Anthropic skip | × | ✓ | ✓ | ✓ | ✓ | ✓ | 5/6 free path |
| 1 free missing | ✓ | × | ✓ | ✓ | ✓ | ✓ | 5/6, gri Groq disabled |
| 3 free missing | ✓ | × | × | × | ✓ | ✓ | 3/6 |
| 5 free missing | ✓ | × | × | × | × | × | 1/6 (Anthropic only) |
| All free missing | × | × | × | × | × | × | UI gracefully degraded |
| Custom 6/6 invalid | invalid×6 | | | | | | UI shows invalid key error |

`mcp__abs__quota_status` ile `configured:bool` doğrulaması her sağlayıcı için.

### 1.3 LICENSE JWT GATING — full lifecycle
- Fresh activation (bootstrap)
- Expiry boundary (now-1s, now+0s, now+1s, now+24h)
- Revoke + re-issue
- Tampered token reject
- 100-year expiry guard (Q12-L21-003 LOW non-bug pin'lendi, hala gerekli)

### 1.4 MAGIC-LINK MULTI-ADMIN SIGNUP FULL FLOW
- Admin A signup → magic link email → claim → /panel
- Token rotate (24h expiry, claim sonrası reuse 401)
- Admin A → Admin B davet → tek tenant 2 admin
- Cross-tenant block (tenant A admin tenant B'ye giremez)

### 1.5 HELM CHART DRY-RUN — K8s 1.27/1.28/1.29
```bash
cd infra/helm/abs
helm lint .
helm template . --debug --dry-run > /tmp/helm-render.yaml
# 3 K8s sürüm dry-run:
for v in 1.27 1.28 1.29; do
  echo "=== K8s $v ==="
  kubectl --context kind-$v apply --dry-run=server -f /tmp/helm-render.yaml || echo "FAIL $v"
done
```

Schema mismatch / deprecated API kullanımı tespit + fix.

### 1.6 PRICING AUDIT — repo'da hardcoded fiyat YOK kontrolü
Memory: `project_tester_handoff_plan.md`. Tester'a verilmeden önce repo'da hardcoded fiyat kalmamalı.

```bash
grep -rnE "\\\$[0-9]+|[0-9]+ ?USD" core/backend/app core/landing/app core/landing/components 2>&1 | grep -v "test\|spec\|\.test\.\|fixture\|mock\|cost.*\$0\|approximate\|ollama_first|free tier" | head -50
```

Bulunan hardcoded değerleri **env var / config** olarak taşı:
- `billing_v10/seats.py` `monthly_price_usd=299.0` → `settings.abs_seat_price_self_host`
- `mcp/tools/status_tools.py` `price_map = {...}` → settings
- `static/admin/index.html` `total * 25` revenue widget → env multiplier
- Email template `$49/year maintenance` → template variable

Pricing tier ID'ler ("self-host", "team-5", "team-10") kalır — bunlar SKU id, fiyat değil. Sadece dolar değerleri çıkar.

---

## 2. FOUNDER GATE — KARAR ZAMANI (LOW, founder dedi devam)

Founder S9'da L21 + Mutmut için yine "devam" dedi → SKIP commit. 5/5 session SKIP, persist note.

---

## 3. ROUND DÖNGÜSÜ

1. Validation pick (öncelik: setup wizard E2E → provider degradation → license JWT → magic-link → Helm dry-run → pricing audit)
2. Mevcut sistem üzerinde DOĞRULAMA — yeni test layer ekleme
3. Bulgu varsa fix + atomic commit
4. **Image rebuild + container exec** (backend dokunulduysa)
5. Round summary `artifacts/sprint_q12/round_<N>_<focus>.md`
6. master_audit_summary.md canlı güncelle

---

## 4. BAŞLANGIÇ ROUND'LARI

### Round 76 = Setup wizard E2E full sweep (11 step Playwright)
EN ÖNCELİKLİ. Tek spec, 11 step, FAIL olursa production-ready değil.

### Round 77 = Provider degradation matrix 7 senaryo
Memory feedback_provider_degradation_test'e göre 7 senaryo + UI gri/disabled doğrulaması.

### Round 78 = License JWT full lifecycle
4 expiry boundary + revoke/re-issue + tamper reject + 100y guard.

### Round 79 = Magic-link multi-admin signup
Tek-tenant 2 admin + cross-tenant block.

### Round 80 = Helm chart K8s 1.27/1.28/1.29 dry-run

### Round 81 = Pricing audit + extract → env var
Backend hardcoded değerleri config'e taşı (billing_v10/seats.py, status_tools.py, admin/index.html widget, email templates).

### Round 82 = fs-scan honest 89 → 95+ (S9'a ek polish)

### Round 83 = L21 + Mutmut SKIP commit (5/5 session)

---

## 5. DELEGATION ZORUNLU (%70+ MCP)

- Setup wizard E2E: `mcp__abs__write_tests` + `mcp__abs__ask_kimi` (Playwright)
- Provider degradation: `mcp__abs__qual_analysis` + `mcp__abs__quota_status` MCP
- Helm/K8s: `mcp__abs__ask_gptoss`
- Pricing audit: `mcp__abs__code_review` + `mcp__abs__ask_qwen32b` (env var pattern)
- License JWT: `mcp__abs__ask_gptoss` (boundary cases)
- Patch judge: `mcp__abs__judge_patch`

---

## 6. KESİN YASAK

- Yeni test layer ekleme — Session 9 = mevcut sistemi DOĞRULAMA
- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- L21 + Mutmut + DR actual: founder approval olmadan ÇALIŞTIRILMASIN
- Helm dry-run actual deploy DEĞİL — production cluster'a dokunma
- Pilot/market/outreach gündem dışı (memory feedback_no_pilot_market_focus)
- Pricing audit: pricing tier ID'leri ("self-host", "team-5") kalır, sadece dolar değerleri çıkar

---

## 7. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3457 (worker spawn, hung self-restart yetkilisin)
- Cookie: admin@demo-acme.com / DemoPass2026!
- Setup wizard E2E için yeni temiz fresh tenant gerekirse:
  ```bash
  # Isolated namespace q12-s9-setup pattern (R34/R75 patterns)
  ABS_DRILL_PROJECT=q12-s9-setup ABS_DRILL_PORT=28100 ...
  ```

---

## 8. BAŞARI KRİTERİ (Session 9 = production readiness)

- Setup wizard E2E 11 step PASS (tek spec)
- Provider degradation 7/7 senaryo PASS
- License JWT 4 expiry + revoke + tamper + 100y guard PASS
- Magic-link 2-admin tenant + cross-tenant block PASS
- Helm K8s 1.27/1.28/1.29 dry-run PASS
- Pricing audit: hardcoded $ değerleri 0 (env var'a taşındı, repo'da grep boş)
- fs-scan honest score 95+ (kalan 6 gap close)
- Image rebuild gate korundu

---

## 9. PRIORITY (Session 9 = production readiness)

**HIGH (tester teslimat eşiği):**
1. Setup wizard E2E full sweep (11 step Playwright)
2. Provider degradation matrix 7 senaryo
3. License JWT full lifecycle
4. Magic-link multi-admin
5. Helm K8s 1.27/1.28/1.29 dry-run
6. Pricing audit + extract

**MEDIUM:**
7. fs-scan honest 89 → 95+ polish

**LOW:**
8. L21 + Mutmut SKIP commit (founder devam dedi, 5/5)

---

## 10. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 10.

Bu session sonunda **tester teslimat eşik checklist** oluşturulacak (memory'deki `project_tester_handoff_plan.md` kriterlerinden).

---

## 11. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -75
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_9.md
```

Round 76 = Setup wizard E2E full sweep'ten başla. Tek Playwright spec. FAIL olursa production-ready değil — fix gerek. Her step'te image rebuild gerekirse evidence yaz.

Engelleyici YOK. Brief eksiksiz. **Bu session, tester teslimat eşiğine yaklaşma session'ı.**
