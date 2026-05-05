# Founder Tester Session — Fix Round 1 (3 bug + page title sweep)

> **Tetikleyici (2026-05-05):** Founder local'de gerçek tester gibi tüm provider key'leri set edip Playwright ile login + 14 sayfa walkthrough yaptı. 3 gerçek bug + 1 sweep iyileştirme tespit edildi.
>
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD 4b4dd92, 100+ commit)
> **Test ortamı:** infra-backend-1 :8000 (image rebuild edilmiş, 8/8 provider key live), Next dev :3457, Playwright headed.

---

## 0. ⚠️ DOĞRULAMA DİSİPLİNİ (S5+S10+S11 tekrarı)

Her fix sonrası:
1. Image rebuild (backend dokunulduysa): `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend`
2. Container exec verify
3. Frontend dokunulduysa Next dev :3457 hot reload doğrula
4. **Full pytest** (selective subset YASAK):
   ```bash
   cd core/backend && ./.venv/bin/python -m pytest --no-header -q \
     --ignore=tests/test_providers.py \
     --ignore=tests/test_q03_real_saas_backends.py \
     --ignore=tests/test_update_channel.py
   ```
   Round summary: `pytest_full_suite: <X> / <Y fail> / <Z error>`. **0 fail + 0 error olmadan ship YASAK.**
5. Founder Playwright session yeniden çalıştırılacak — fix'in canlı path'te çalıştığını doğrulayacak.

---

## 1. BUG LİSTESİ (founder Playwright walkthrough'tan)

### 🔴 BUG-1 HIGH — Login redirect logic eksik
**Symptom:** Founder `/login` sayfasında email + password girip submit'e bastı.
- Backend auth başarılı (cookie set edildi — sonra direkt `/panel` URL'sine giderse tüm sayfalar render ediyor).
- AMA frontend submit sonrası URL `/login`'de takılı kaldı, kullanıcıya hiçbir feedback yok.
- Müşteri "giriş yap" → ekranda hiçbir şey değişmedi → kafası karışır.

**Surface:** `core/landing/app/login/page.tsx` veya altındaki form component.
**Beklenen:** Submit başarılı + 200 cookie → `router.push('/panel')` (Next 14+ App Router) ya da `window.location.href = '/panel'`.

**Test:**
```ts
// __tests__/playwright/founder_test_fix_login.spec.ts
test('login form redirects to /panel on success', async ({ page, baseURL }) => {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'admin@demo-acme.com');
  await page.fill('input[type="password"]', 'DemoPass2026!');
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/panel/, { timeout: 10000 });
  expect(page.url()).toMatch(/\/panel/);
});
```

### 🔴 BUG-2 HIGH — /admin/marketplace page.goto 30s timeout
**Symptom:** Founder Playwright session `/admin/marketplace` sayfasına `goto({ waitUntil: 'domcontentloaded', timeout: 30000 })` ile gitti, **30s'de domcontentloaded gelmedi.** Diğer 14 sayfa hepsi 2-3s içinde render etti, tek bu sayfa takılı.

**Hipotezler (worker tespit edip fix etsin):**
- A) SSR fetch heavy/blocking (e.g., marketplace catalog 100+ entry parallel render-blocking)
- B) Upstream 5xx (Cerbos / NATS / DB) → Next 15 SSR retry'da hang
- C) Infinite loop in component mount (useEffect → re-render cycle)
- D) Missing /v1/marketplace endpoint → frontend proxy hangs

**Investigation komutu:**
```bash
# Backend cevap veriyor mu doğrula
curl -sk -b /tmp/founder_cookie.txt http://localhost:8000/v1/marketplace -m 5 -w "\nstatus=%{http_code} time=%{time_total}\n"

# Next dev console
tail -f /tmp/next_dev_3457.log | grep -E "marketplace|error|warn"

# Sayfa fetch trace
node -e "const {chromium} = require('playwright'); (async () => {
  const b = await chromium.launch({headless: true});
  const p = await b.newPage();
  p.on('request', r => console.log('REQ', r.url()));
  p.on('response', r => console.log('RES', r.status(), r.url()));
  await p.goto('http://localhost:3457/admin/marketplace', {waitUntil: 'domcontentloaded', timeout: 60000}).catch(e => console.log('ERR', e.message));
  await b.close();
})();"
```

**Beklenen fix:**
- SSR data fetch'i `Suspense + streaming` ile böl (Next 15 RSC pattern)
- Veya `generateStaticParams` yerine client-side fetch ile başlat
- Loading skeleton göster

**Test:**
```ts
test('admin/marketplace renders within 5s', async ({ page }) => {
  await page.goto('/admin/marketplace', { waitUntil: 'domcontentloaded', timeout: 5000 });
  await expect(page.locator('h1')).toBeVisible();
});
```

### 🟡 BUG-3 MED — Chat send button discoverability
**Symptom:** `/panel/chat` 25 button ile render edildi ama Playwright `button:has-text("Gönder|Send")` selector'ı bulamadı.
- Muhtemelen icon-only (paper plane SVG) button, accessible label yok.
- Screen reader'lar için a11y problem; Playwright/test selector için ZORLUK.

**Fix:**
```tsx
// core/landing/app/panel/chat/ChatInput.tsx
<button type="submit" aria-label="Mesaj gönder" data-testid="chat-send" ...>
  <SendIcon />
</button>
```

`aria-label="Mesaj gönder"` (TR locale) + `data-testid="chat-send"` ekle. ES/EN için locale-aware ya t() ile.

**Test:**
```ts
test('chat send button has accessible label', async ({ page }) => {
  await page.goto('/panel/chat');
  const send = page.locator('[data-testid="chat-send"]');
  await expect(send).toBeVisible();
  await expect(send).toHaveAttribute('aria-label', /gönder|send|enviar/i);
});
```

### 🟢 SWEEP — Page title parity
**Symptom:** 14 sayfadan 13'ü default title `Automatia ABS — Self-hosted AI ağı` kullanıyor, sadece `/admin/workflow-builder` özel title `Workflow Builder — ABS Admin · Automatia ABS` veriyor.

**Fix:** Her panel/admin sayfası kendi `metadata.title` export'unu ship etsin (Next App Router pattern).

```tsx
// core/landing/app/panel/chat/page.tsx
export const metadata: Metadata = {
  title: 'Sohbet — ABS Panel',
};
```

13 sayfa × atomic commit veya tek bulk commit (worker tercih). Locale-aware ise i18n key'ten gelsin.

**Test:**
```ts
const TITLES = {
  '/panel': /Genel Bakış|Dashboard/,
  '/panel/chat': /Sohbet|Chat/,
  '/panel/tools': /MCP Tool/,
  // ...13 entry
};
test.describe('every panel/admin page has unique title', () => {
  for (const [path, expected] of Object.entries(TITLES)) {
    test(`${path} title`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveTitle(expected);
    });
  }
});
```

---

## 2. EVIDENCE (founder Playwright session)

- Bug raporu JSON: `/tmp/founder_test_bugs.json` (3 entry)
- Screenshot'lar: `/Users/eneseserkan/Desktop/Digisfer Inc/feat_*.png` (17 dosya — 14 sayfa + login + chat steps)
- Test log: `/tmp/founder_feature_test.log`

Hipotez bisecte gerekirse worker bunlara bakar.

---

## 3. ROUND DÖNGÜSÜ (S3-S12 disiplini)

1. Bug pick (öncelik: BUG-2 marketplace timeout → BUG-1 login redirect → BUG-3 chat label → SWEEP titles)
2. Root cause + minimal atomic fix
3. **Image rebuild + Next reload + container exec verify**
4. Yeni test (yukarıdaki spec'lerin canlı PASS olduğunu doğrula)
5. Full pytest GREEN doğrula
6. Round summary `artifacts/founder_test_fix_1/round_<N>.md` — `pytest_full_suite:` zorunlu satır
7. **Selective subset YASAK** (S11 dersi)

---

## 4. ROUND BAŞLANGIÇ

### Round 1 = BUG-2 marketplace timeout
İlk koşul fetch trace al → root cause tespit → fix → 5s < goto verify.

### Round 2 = BUG-1 login redirect
`/login` form submit handler'da `router.push('/panel')` veya equivalent. Test PASS.

### Round 3 = BUG-3 chat send button accessibility
`aria-label` + `data-testid` ekle. Test PASS.

### Round 4 = SWEEP page titles
13 panel/admin sayfasına metadata.title ekle. Bulk veya per-page atomic.

### Round 5 = Final founder Playwright session re-run
Founder otomasyon yeniden çalıştırılacak — bu round'da DEĞİL, founder yapacak.

---

## 5. KESİN YASAK

- **Selective subset rapor → FULL CLEAN sayma** (S11 dersi, 4. tekrar)
- "Shipped + test PASS standalone" ≠ "live path works"
- Image rebuild gate her backend round
- Pilot/market/outreach gündem dışı
- L21 + Mutmut + DR actual: founder approval yok

---

## 6. DELEGATION ZORUNLU (%70+ MCP)

- Root cause analysis (marketplace timeout): `mcp__abs__ask_gptoss`
- Next.js App Router redirect pattern: `mcp__abs__ask_kimi`
- A11y aria-label TR/EN/ES: `mcp__abs__ask_qwen32b`
- Page title metadata pattern: `mcp__abs__ask_kimi`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Patch judge: `mcp__abs__judge_patch`

---

## 7. BAŞARI KRİTERİ

- BUG-2 marketplace render < 5s (founder verify)
- BUG-1 login → /panel redirect (founder verify)
- BUG-3 chat send `aria-label` + `data-testid` (Playwright PASS)
- 13 panel/admin sayfası özel title
- Backend pytest 1755 → ≥1755 (regresyon yok, +4 yeni test eklenecek)
- Image rebuild + container exec evidence per backend round
- 0 fail + 0 error full suite

---

## 8. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -5
cat _agent-tasks/WORKER_FOUNDER_TEST_FIX_1.md
cat /tmp/founder_test_bugs.json
ls /Users/eneseserkan/Desktop/Digisfer\ Inc/feat_*.png | head
```

Round 1 = BUG-2 marketplace timeout investigation + fix'ten başla. Engelleyici YOK.

---

**Founder devam:** Worker fix'leri shipliyince founder Playwright session yeniden çalıştırılacak (gerçek tester) + sonra cascade routing + RAG + workflow gerçek output kalitesi + token tasarrufu doğrulanacak. **Bu test loop'u tester teslimat eşik gerçek MÜHÜR.**
