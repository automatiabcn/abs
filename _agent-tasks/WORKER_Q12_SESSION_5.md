# Q12 Session 5 — Kalan Layer + Mutation + Multi-Failure Chaos

> **Tetikleyici:** Q12 Session 4 — 4 atomic round (R26-R29) + flaky widen + closing summary. **L22 + L25 → 3/3 FULL CLEAN ⭐⭐** (8 Q12 layer FULL CLEAN total: L17-L20, L22-L25). 4 HIGH bug shipped (Q12-L22-005/006 OAuth replay, Q12-L25-004/005 admin/RAG body DoS). Backend pytest 1579 → 1611 (+32).
> **Hedef:** L26 sweep 2 (30dk Playwright + heap snapshot) + mutmut L1 (cascade + auth) + L21 sweep 3 destructive (founder-gated) + Q12 L17-L20 deep round 4-5 (multi-failure cascade + SW cache).
> **Branch:** `feat/sprint-q12-deep-quality` (Session 1+2+3+4 = 30+ commit shipped)

---

## 0. ⚠️ IMAGE REBUILD GATE (Session 3+4 zafer — devam)

S3 6/6 round + S4 3/3 backend round image rebuild + container exec evidence yapıldı. Aynı disiplin S5'te DEVAM:

```bash
cd /Users/eneseserkan/Main/abs-server-product
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend
docker exec infra-backend-1 test -f /app/<yeni dosya> && echo "IMAGE OK"
docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"
```

Round summary'ye `image_rebuilt_at:` + `container_pytest_pass:` zorunlu satırlar.

---

## 1. ÖNCELIK — KALAN LAYER (HIGH)

### L26 sweep 2 — 30dk Playwright + heap snapshot (S3+S4'te defer edildi)
S2'de typed JWT exceptions kapatıldı. Sweep 2 = gerçek 30dk Chromium long-running session test.

```ts
// __tests__/playwright/q12-l26-long-running.spec.ts
test('30dk panel chat tab idle survives token refresh + heap drift', async ({ page, context }) => {
  test.slow();
  test.setTimeout(35 * 60 * 1000);

  await page.goto('http://localhost:3000/panel/chat');
  await page.waitForSelector('[data-testid="chat-input"]', { timeout: 60000 });

  const heap0 = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);

  await page.waitForTimeout(30 * 60 * 1000);

  const heap1 = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);
  console.log('heap_baseline_mb', heap0 / 1024 / 1024, 'heap_30dk_mb', heap1 / 1024 / 1024);

  const status = await page.evaluate(() =>
    fetch('/v1/chat/sessions', { credentials: 'include' }).then(r => r.status)
  );
  expect(status).toBe(200);
  expect(heap1 - heap0).toBeLessThan(50 * 1024 * 1024);  // 50MB drift bound
});

test('WebSocket reconnect after backend kill', async ({ page }) => {
  await page.goto('http://localhost:3000/panel/chat');
  // Backend container restart (separate test setup script)
  // Frontend should auto-reconnect SSE within 5s
});
```

Frontend dev server zaten port 3000'de canlı. Headed Chromium overhead için Playwright config'te `workers: 1` + `timeout: 35min`.

### L21 sweep 3 — DESTRUCTIVE founder-gated drill
Founder onayı gerekli (volume wipe). Brief'te yer al ama **`SKIP=true` flag'i ile shipped olmasın** — sadece spec ship + Founder approval bekle:

```bash
# scripts/destructive_drill.sh (DRY RUN by default, founder ABS_DESTRUCTIVE_DRILL=1 ile aktif)
[ "$ABS_DESTRUCTIVE_DRILL" = "1" ] || { echo "SKIP — founder approval required"; exit 0; }

docker compose -f infra/docker-compose.yml down --volumes
rm -rf core/backend/data/*.db
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build
sleep 30

# Re-init pipeline:
curl -X POST http://localhost:8000/setup/init -d '...'
curl -X POST http://localhost:8000/auth/signup -d '...'
# Magic link onay → setup wizard → license activate → cascade ping
```

3 iterasyon. Round summary'ye `destructive_drill: SKIPPED|RAN_<n>` belirt.

---

## 2. INHERITED Q10/Q11 — MUTATION TESTING (HIGH)

S3+S4'te defer. S5'te ZORUNLU — kalite floor.

```bash
cd core/backend
./.venv/bin/pip install mutmut==2.4.5
./.venv/bin/mutmut run --paths-to-mutate=app/cascade/ --tests-dir=tests/ --runner='./.venv/bin/pytest -x'
./.venv/bin/mutmut results | head -30
# Surviving mutant başına 1 yeni boundary test ekle (mutmut show <id> ile görüntüle)
```

İkinci hedef module: `app/api/auth/` (security-critical). Tek session'da 2 module yeter.

Beklenen: 5-30 surviving mutant. Her biri için fixate eden test ship.

---

## 3. Q12 L17-L20 DEEP ROUND 4-5 (MEDIUM)

| Layer | Round 4-5 derinleştirme |
|-------|--------------------------|
| L17 break-even | S4'te BodySizeLimitMiddleware eklendi — bundle impact ölç. Decision matrix güncelle. |
| L18 cold-cache | Service Worker cache strategy implementation: /panel/chat (cache-first), /panel/dashboard (network-first), /panel/rag (stale-while-revalidate). |
| L19 backwards compat | Q12-L22-005/006/004 OAuth replay + Q12-L25-004/005 body DoS için explicit regression test. |
| L20 chaos | Multi-failure simultaneous: backend kill + DB lock + Redis down → cascade UI graceful? Recovery time. |

---

## 4. ROUND DÖNGÜSÜ

1. Layer pick (öncelik: L26 sweep 2 → mutmut cascade → mutmut auth → L20 multi-failure → L18 SW cache → L21 destructive)
2. Real bug hunt (spec ship YETERSİZ)
3. **Image rebuild + container exec** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** + **dış-curl smoke**
6. Round summary `artifacts/sprint_q12/round_<N>_<layer>.md` — `image_rebuilt_at:` + `container_pytest_pass:` zorunlu
7. master_audit_summary.md canlı güncelle

---

## 5. BAŞLANGIÇ ROUND'LARI

### Round 30 = L26 sweep 2 (30dk Playwright)
Yukarıdaki spec'i `__tests__/playwright/q12-l26-long-running.spec.ts` olarak ship. Heap drift + token auto-refresh + endpoint 200 doğrula.

### Round 31 = mutmut L1 cascade module
```bash
cd core/backend
./.venv/bin/mutmut run --paths-to-mutate=app/cascade/ --tests-dir=tests/cascade/
./.venv/bin/mutmut results
# Surviving mutant'lar için yeni boundary test ekle
```

### Round 32 = mutmut L1 auth module
```bash
./.venv/bin/mutmut run --paths-to-mutate=app/api/auth/ --tests-dir=tests/
./.venv/bin/mutmut results
```

### Round 33 = L20 multi-failure simultaneous chaos
```ts
test('multi-failure: backend 503 + DB lock + Redis down → graceful UI', async ({ page }) => {
  // Inject 3 simultaneous failures, verify chat UI shows error tile + retry CTA
  // No white screen, no infinite spinner, no console error explosion
});
```

### Round 34 = L18 SW cache strategy implementation
3 strategy ship (`core/landing/public/sw.js`):
- /panel/chat → cache-first (offline draft)
- /panel/dashboard → network-first (real-time)
- /panel/rag → stale-while-revalidate (background sync)

### Round 35 = L21 sweep 3 destructive drill spec (founder-gated)
`scripts/destructive_drill.sh` ship + 3 iterasyon spec. Founder approval bekle.

---

## 6. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Race condition reasoning: `mcp__abs__ask_gptoss`
- Multi-failure chaos: `mcp__abs__qual_analysis`
- Playwright async: `mcp__abs__ask_kimi`
- Mutation testing: `mcp__abs__ask_gptoss`
- Service Worker pattern: `mcp__abs__ask_gptoss` (cache strategies + offline)
- Patch judge: `mcp__abs__judge_patch`

---

## 7. KESİN YASAK (Q7+Q8+...+Q12 S4 dersleri)

- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- Selective subset ≠ FULL CLEAN
- Spec ship ≠ round ilerletti
- Container 46h+ ≠ live (S2 dersi)
- Pilot/market/outreach gündem dışı
- Destructive drill founder approval YOK ise SHIP edilmesin (env flag default skip)

---

## 8. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3000 (canlı, 30dk Playwright için ZORUNLU)
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s5_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```

---

## 9. BAŞARI KRİTERİ (Session 5 hedefi)

- L26 → 2/3 (30dk Playwright + heap snapshot ship)
- Mutmut 2 round (cascade + auth, surviving mutant başına test)
- L20 multi-failure chaos round 4 (deep)
- L18 SW cache implementation (3 strategy ship)
- L21 destructive drill spec (founder-gated, ABS_DESTRUCTIVE_DRILL=0 default)
- Backend pytest ≥1635 (şu an 1611, hedef +24)
- 5+ yeni real bug
- Image rebuild gate her backend round (S3+S4 disiplini devam)

---

## 10. PRIORITY (Session 5 odak)

**HIGH:**
1. L26 sweep 2 — 30dk Playwright + heap drift + WebSocket reconnect
2. Mutmut L1 cascade module — kalite floor
3. Mutmut L1 auth module — security floor

**MEDIUM:**
4. L20 multi-failure cascade chaos round 4
5. L18 Service Worker cache strategies (3 route group)
6. L21 destructive drill spec (founder-gated)

**LOW:**
7. L19 explicit regression test'ler S4 HIGH bug'lar için
8. L17 break-even decision matrix S4 sonrası refresh

---

## 11. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 6.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 12. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -30
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_5.md
```

Round 30 = L26 sweep 2 (30dk Playwright + heap snapshot)'tan başla. Atomic commit per round.
Image rebuild + container exec evidence ZORUNLU (S3+S4 disiplini).

Engelleyici YOK. Brief eksiksiz.
