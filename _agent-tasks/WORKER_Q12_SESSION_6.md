# Q12 Session 6 — Q12-L20-003 Frontend Fix + SW Cache + Inherited Deep + L21 Actual Drill

> **Tetikleyici:** Q12 Session 5 — 5 atomic round (R30-R34) shipped. **L21 → 3/3 ⭐ spec** (9 Q12 layer FULL CLEAN total: L17-L25). 1 MED bug (Q12-L20-003 chat hang under multi-503). Backend pytest 1611 → 1630 (+19) + 6 Playwright. L26 → 2/3.
> **Hedef:** Q12-L20-003 frontend fix (real bug shipped via test.fail) + L18 Service Worker cache impl + L26 sweep 3 (30dk EMPIRICAL real Chromium run) + L21 destructive drill ACTUAL run (founder approval) + inherited Q10/Q11 advanced fuzz.
> **Branch:** `feat/sprint-q12-deep-quality` (Session 1+2+3+4+5 = 35+ commit shipped)

---

## 0. ⚠️ IMAGE REBUILD GATE (S3+S4+S5 sürekli zafer — devam)

S3 6/6 + S4 3/3 + S5 backend round'larında image rebuild evidence. Aynı disiplin S6'da DEVAM:

```bash
cd /Users/eneseserkan/Main/abs-server-product
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend
docker exec infra-backend-1 test -f /app/<yeni dosya> && echo "IMAGE OK"
docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"
```

Round summary'ye `image_rebuilt_at:` + `container_pytest_pass:` zorunlu.

---

## 1. ÖNCELIK — REAL BUG FIX + DEFERRED (HIGH)

### Q12-L20-003 frontend fix — chat hangs under multi-503 (S5 buldu, fix BEKLİYOR)
S5 R32 multi-failure chaos `__tests__/playwright/q12-l20-chaos-multi.spec.ts` test.fail() ile documented. Root cause: `SessionsList` component `useSWR` 503 hata path'inde error throw etmiyor — `<Suspense>` boundary "Yükleniyor..." spinner'da takılı kalıyor. Chat error tile mount olmuyor.

**Fix surface:**
```ts
// core/landing/app/panel/chat/SessionsList.tsx
const { data, error, isLoading } = useSWR('/v1/chat/sessions', fetcher, {
  shouldRetryOnError: false,  // 503 → don't infinite-retry
  errorRetryCount: 2,
  onError: (err) => {
    // Surface to chat-error-tile via shared context
    chatErrorContext.setError({ source: 'sessions', code: err.status, message: err.message });
  },
});
if (error) return <ChatErrorTile reason="sessions_unavailable" retry={mutate} />;
```

`test.fail()` → `test()` upgrade + Q12-L20-003 PASS olduğunu doğrula.

### L18 Service Worker cache implementation (S5'te defer)
3 strategy ship (`core/landing/public/sw.js`):
- `/panel/chat` → cache-first (offline draft)
- `/panel/dashboard` → network-first (real-time)
- `/panel/rag` → stale-while-revalidate (background sync)

Workbox config + Next.js custom service worker registration. Test: offline mode + cache hit/miss assertions.

### L26 sweep 3 — 30dk EMPIRICAL real Chromium run (S5 sweep 2 spec ship'ti, sweep 3 actual run)
S5 R30 gated test 30dk empirical idle test'i mevcut ama gate'li. Sweep 3 = gerçek 30dk run + heap snapshot + WebSocket reconnect drill empirical.

```bash
ABS_E2E_LONG=1 npx playwright test __tests__/playwright/q12-l26-long-running.spec.ts \
  --workers=1 --timeout=2100000  # 35 min total
```

3 gerçek senaryo:
1. 30dk panel/chat tab idle → token auto-refresh + heap drift < 50MB
2. Backend kill mid-session → SSE reconnect within 5s
3. WebSocket reconnect after Caddy restart

### L21 sweep 4 — ACTUAL destructive drill run (founder approval bekliyor)
S5 R34 spec ship + isolated namespace (`q12-l21-drill` + port 28000). Founder onaylarsa actual 3-iterasyon run:

```bash
ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash scripts/chaos/destructive_drill.sh
```

**FOUNDER ONAY GEREKLİ** — bu komutu çalıştırmadan önce founder'a sor. Onay yoksa SKIP, `L21_destructive_run: SKIPPED — pending founder approval` not düş.

---

## 2. INHERITED Q10/Q11 — ADVANCED FUZZ + A11Y DEEP (MEDIUM)

### Q11 L13 fuzz — Hypothesis 10000 iter (S2'de plan, hala defer)
```python
from hypothesis import given, strategies as st, settings

@given(st.text(min_size=1, max_size=10000))
@settings(max_examples=10000, deadline=None)
def test_chat_completion_no_500_on_arbitrary_input(content):
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": content}]})
    assert r.status_code in (200, 400, 422, 429), f"500 OOM on input len {len(content)}"
```

`app/cascade/router.py` + `app/api/rag.py` + `app/api/workflows.py` her biri için 10K iterasyon.

### Q10 L4 a11y deep — Manual screen reader sim (NVDA aria announcements)
axe-core sweep ⭐ FULL CLEAN ama screen reader davranışı manuel test edilmedi. Spec:
```ts
test('aria-live announcements fire on chat send', async ({ page }) => {
  await page.goto('/panel/chat');
  // Capture all aria-live region updates during 3-message conversation
  const updates = await page.evaluate(() => {
    const region = document.querySelector('[aria-live="polite"]');
    // ... capture updates
  });
  expect(updates).toContain('Sending message');
  expect(updates).toContain('Response received');
});
```

---

## 3. MUTMUT CI PATTERN (LOW — ASYNC)

S5'te full mutmut runtime overhead (16-24min/module). Çözüm: weekend CI cron job.
```yaml
# .github/workflows/mutation-weekend.yml
on:
  schedule:
    - cron: '0 2 * * SAT'  # weekend 02:00
jobs:
  mutmut:
    runs-on: ubuntu-latest
    timeout-minutes: 240
    steps:
      - run: cd core/backend && mutmut run --paths-to-mutate=app/cascade/
      - run: mutmut results > /tmp/mutmut-report.txt
      - uses: actions/upload-artifact@v4
        with: { name: mutmut-report, path: /tmp/mutmut-report.txt }
```

Spec ship + GitHub Actions config. Actual run weekend tetiklenir.

---

## 4. ROUND DÖNGÜSÜ

1. Layer pick (öncelik: Q12-L20-003 fix → L18 SW cache → L26 sweep 3 → L21 actual drill (founder onay) → fuzz → a11y → mutmut CI)
2. Real bug hunt (spec ship YETERSİZ)
3. **Image rebuild + container exec** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** + **dış-curl smoke**
6. Round summary `artifacts/sprint_q12/round_<N>_<layer>.md` — `image_rebuilt_at:` + `container_pytest_pass:` zorunlu
7. master_audit_summary.md canlı güncelle

---

## 5. BAŞLANGIÇ ROUND'LARI

### Round 35 = Q12-L20-003 frontend fix
SessionsList.tsx `useSWR` error handling + ChatErrorTile mount path. test.fail() → test() upgrade.

### Round 36 = L18 SW cache impl
3 strategy ship + offline mode test.

### Round 37 = L26 sweep 3 actual 30dk run
`ABS_E2E_LONG=1` ile 3 senaryo empirical run + heap snapshot data. Round summary'ye gerçek heap drift mb değeri yaz.

### Round 38 = L21 actual destructive drill (founder onay)
Sor → onaylarsa 3 iterasyon → onaylanmazsa SKIP commit (spec ile L21 3/3 zaten ship'li).

### Round 39 = Q11-L13 hypothesis 10K fuzz
Cascade router + RAG + workflows için Hypothesis 10K iter.

### Round 40 = Q10-L4 a11y deep — screen reader aria-live capture
3-5 senaryo Playwright spec.

### Round 41 = Mutmut CI weekend pattern
GitHub Actions yaml + spec ship.

---

## 6. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- SWR error handling: `mcp__abs__ask_kimi` (React patterns)
- SW cache strategies: `mcp__abs__ask_gptoss` (Workbox + offline)
- Hypothesis fuzz: `mcp__abs__ask_gptoss`
- A11y aria-live: `mcp__abs__ask_qwen32b` (TR + EN + ES locale)
- Patch judge: `mcp__abs__judge_patch`

---

## 7. KESİN YASAK (Q7+...+Q12 S5 dersleri)

- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- Selective subset ≠ FULL CLEAN
- Spec ship ≠ round ilerletti (Q12-L20-003 fix ZORUNLU, sadece test.fail upgrade değil)
- Pilot/market/outreach gündem dışı
- L21 destructive drill ACTUAL run founder approval olmadan ÇALIŞTIRILMASIN
- L26 sweep 3 actual run = 30dk gerçek browser, gated test'i atla DEĞİL (sweep 3 = empirical run)

---

## 8. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3000 (canlı, L26 sweep 3 + L20-003 + L18 SW için ZORUNLU)
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s6_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```
- Destructive drill (founder onay sonrası): `ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash scripts/chaos/destructive_drill.sh`

---

## 9. BAŞARI KRİTERİ (Session 6 hedefi)

- Q12-L20-003 fix shipped + test.fail() → test() upgrade PASS
- L18 SW cache 3 strategy implementation + offline mode test
- L26 sweep 3 ACTUAL 30dk run (heap snapshot mb data + reconnect timing)
- L21 sweep 4 actual destructive run (founder onay) → L21 → 4/3 deep
- Q11-L13 fuzz 10K iter cascade + RAG + workflows
- Q10-L4 a11y deep aria-live capture
- Mutmut CI weekend pattern shipped
- Backend pytest ≥1655 (şu an 1630, hedef +25)
- 5+ yeni real bug
- Image rebuild gate her backend round

---

## 10. PRIORITY (Session 6 odak)

**HIGH:**
1. Q12-L20-003 frontend fix (S5 real bug, fix BEKLİYOR)
2. L18 Service Worker cache impl
3. L26 sweep 3 ACTUAL 30dk empirical run
4. L21 sweep 4 ACTUAL destructive drill (founder onay)

**MEDIUM:**
5. Q11-L13 hypothesis 10K fuzz
6. Q10-L4 a11y deep aria-live capture

**LOW (async):**
7. Mutmut CI weekend pattern (GitHub Actions yaml)

---

## 11. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 7.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 12. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -35
cat artifacts/sprint_q12/master_audit_summary.md
cat artifacts/sprint_q12/session_5_complete.md
cat _agent-tasks/WORKER_Q12_SESSION_6.md
```

Round 35 = Q12-L20-003 frontend fix'ten başla. test.fail() → test() upgrade + dış-curl smoke verify.
Image rebuild + container exec evidence ZORUNLU.

Engelleyici YOK. Brief eksiksiz.
