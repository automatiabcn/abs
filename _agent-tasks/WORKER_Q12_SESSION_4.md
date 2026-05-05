# Q12 Session 4 — Layer Tamamlama + Inherited Deep + Mutation Testing

> **Tetikleyici:** Q12 Session 3 — 6 atomic round (R20-R25) shipped. L24 3/3 FULL CLEAN ⭐ (6 Q12 layer FULL CLEAN total). 9+1+1 bug (4 HIGH + 4 MED + 2 LOW). Backend pytest 1527 → 1579 (+52). Image rebuild discipline 6/6 round honored.
> **Hedef:** L22 → 3/3 + L25 → 3/3 + L26 sweep 2 (Playwright) + L21 fresh deploy non-destructive expansion + inherited Q10/Q11 mutation testing (mutmut L1).
> **Branch:** `feat/sprint-q12-deep-quality` (Session 1+2+3 üzerinde devam, 25+ commit shipped)

---

## 0. ⚠️ IMAGE REBUILD GATE (Session 3'te zafer — devam)

Session 3'te 6/6 round image rebuild yapıldı, container exec evidence yazıldı. Aynı disiplin Session 4'te DEVAM:

```bash
cd /Users/eneseserkan/Main/abs-server-product
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend
docker exec infra-backend-1 test -f /app/<yeni dosya> && echo "IMAGE OK"
docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"
```

Round summary'ye `image_rebuilt_at:` + `container_pytest_pass:` zorunlu. Eksikse round NOT shipped.

---

## 1. ÖNCELIK — Layer kapanış (HIGH)

### L22 sweep 3 — race condition kalan vektörler
S2 setup wizard TOCTOU + S3 vault rotate concurrent-race kapatıldı. Kalan:
- **OAuth client_id registration race**: 2 admin aynı `client_id` ile create → duplicate? 409? Optimistic lock?
- **Inngest worker idempotency**: aynı `event_id` 3 kez fire → 1 kez execute (dedup key + UNIQUE constraint)?
- **Cascade routing race**: 100 paralel chat req → routing decision deterministic? Provider state machine race?

```python
async def test_concurrent_oauth_client_register():
    barrier = asyncio.Barrier(2)
    async def reg(actor):
        await barrier.wait()
        return await client.post("/v1/admin/oauth/clients", json={"client_id": "shared-x", "name": actor})
    a, b = await asyncio.gather(reg("A"), reg("B"))
    statuses = sorted([a.status_code, b.status_code])
    assert statuses == [200, 409]  # NOT [200, 200] silent overwrite
```

### L25 sweep 3 — boundary payload kalan caps
S2 marketplace InstallBody + S3 workflow execute + chat completions kapatıldı. Kalan:
- **RAG ingest batch DoS**: 100 paralel doc → memory + queue saturation?
- **Plugin install 50MB cap**: marketplace install body `Content-Length` enforce?
- **Workflow nodes count**: synthesize 100 node → execution time?
- **Chat session 1000 msg**: existing 200 cap'i geçici, kalıcı 1000 msg cap + cleanup?

### L26 sweep 2 — long-running session GERÇEK Playwright (S3'te defer edildi)
S2'de typed exceptions yapıldı, S3'te headed Chromium overhead defer ettik. Session 4'te:

```ts
// __tests__/playwright/q12-l26-long-running.spec.ts
test('30dk panel chat tab idle survives token refresh', async ({ page, context }) => {
  test.slow();
  test.setTimeout(35 * 60 * 1000);

  await page.goto('http://localhost:3000/panel/chat');
  await page.waitForSelector('[data-testid="chat-input"]', { timeout: 60000 });

  // Heap baseline
  const heap0 = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);

  // 30dk idle
  await page.waitForTimeout(30 * 60 * 1000);

  // Heap snapshot post-idle
  const heap1 = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);
  console.log('heap_baseline', heap0, 'heap_30dk', heap1, 'delta_mb', (heap1 - heap0) / 1024 / 1024);

  // Token auto-refresh + endpoint hala çalışıyor mu
  const status = await page.evaluate(() =>
    fetch('/v1/chat/sessions', { credentials: 'include' }).then(r => r.status)
  );
  expect(status).toBe(200);

  // Heap drift < 50MB (gevşek bound, 30dk için)
  expect(heap1 - heap0).toBeLessThan(50 * 1024 * 1024);
});
```

Frontend dev server: `cd core/landing && npm run dev`. Background process headless Chromium.

---

## 2. INHERITED Q10/Q11 — MUTATION TESTING (MEDIUM)

L1 unit coverage `mutmut` ile mutation testing — Session 3'te defer. Bu sefer ZORUNLU:

```bash
cd core/backend
./.venv/bin/pip install mutmut==2.4.5
./.venv/bin/mutmut run --paths-to-mutate=app/cascade/ --tests-dir=tests/ --runner='pytest -x'
./.venv/bin/mutmut results | head -20
# Beklenen: 5-30 surviving mutant. Her biri için 1 yeni boundary test ekle.
```

Sadece `app/cascade/` + `app/api/auth/` (security-critical) module'lar için yap. Full repo overkill.

Surviving mutant'ı `mutmut show <id>` ile görüntüle, fixate edecek test yaz.

---

## 3. L21 SAFE EXPANSION (founder-gated kalan dışında)

Session 1'de application-layer drill, Session 2'de defer. Session 4'te:
- **Migration roundtrip 10 kez**: `alembic upgrade head → downgrade -1 → upgrade head` 10 iterasyon idempotent
- **Setup wizard 6-step state**: her step'te kill -9 → resume `completed:true` aynı mı?
- **License JWT expiry edge**: now-1s, now+0s, now+1s, now+24h → boundary case'lerin tutarlı reddi
- **Vault rotation idempotency**: rotate × 5 kez → key 5 farklı, eski versiyonlarla decrypt OK?

Hiçbiri destructive değil — production volume dokunulmuyor.

---

## 4. Q12 L17-L20 DEEP ROUND 4-5 (LOW)

| Layer | Round 4-5 derinleştirme |
|-------|--------------------------|
| L17 break-even | Q12 yeni dynamic import'ları (S3'te eklenen) re-evaluate. Decision matrix güncelle. |
| L18 cold-cache | Service Worker cache strategy implementation: /panel/chat (cache-first), /panel/dashboard (network-first), /panel/rag (stale-while-revalidate). |
| L19 backwards compat | Session 3 HIGH bug'lar (Q12-L22-002, Q12-L25-002, Q12-L25-003) için explicit regression test. |
| L20 chaos | Multi-failure simultaneous: backend kill + DB lock + Redis down → cascade UI graceful? |

---

## 5. ROUND DÖNGÜSÜ (Session 3 disiplini devam)

1. Layer pick (öncelik: L22 sweep 3 → L25 sweep 3 → L26 sweep 2 → mutmut → L21 safe expansion)
2. Real bug hunt (spec ship YETERSİZ)
3. **Image rebuild + container exec** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** (`docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"`)
6. **Dış-curl smoke** + **emit_event count grep** (audit trail evidence)
7. Round summary `artifacts/sprint_q12/round_<N>_<layer>.md` — `image_rebuilt_at:` + `container_pytest_pass:` zorunlu satırlar
8. master_audit_summary.md canlı güncelle

---

## 6. BAŞLANGIÇ ROUND'LARI

### Round 26 = L22 sweep 3 (OAuth client_id race)
```bash
grep -n "POST.*oauth.*client" core/backend/app/api/admin/oauth*.py
grep -n "UNIQUE\|unique=True" core/backend/app/db/models.py | grep -i client
```
DB UNIQUE constraint var mı? IntegrityError caught + 409 mu? Yoksa silent overwrite mı?

### Round 27 = L25 sweep 3 (RAG batch DoS)
```python
async def test_rag_ingest_100_parallel_docs():
    docs = [{"text": f"doc {i} " * 1000} for i in range(100)]
    results = await asyncio.gather(*[client.post("/v1/rag/ingest", json=d) for d in docs])
    statuses = [r.status_code for r in results]
    success_count = statuses.count(200)
    rate_limited = statuses.count(429)
    assert success_count + rate_limited >= 95  # graceful, NOT 500 OOM
```

### Round 28 = L26 sweep 2 (30dk Playwright)
Yukarıdaki spec'i `__tests__/playwright/q12-l26-long-running.spec.ts` olarak ship.

### Round 29 = mutmut L1 mutation testing
```bash
mutmut run --paths-to-mutate=app/cascade/ --tests-dir=tests/
mutmut results | head -10
```
Surviving mutant başına 1 test ekle.

### Round 30 = L21 safe expansion (migration roundtrip 10×)
```bash
for i in {1..10}; do
  alembic upgrade head && alembic downgrade -1 && alembic upgrade head
  echo "iteration $i OK"
done
```

### Round 31+ rotation: Q12 L17-L20 deep round 4 (SW cache veya multi-failure)

---

## 7. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Race condition reasoning: `mcp__abs__ask_gptoss` (deadlock + isolation)
- DoS resilience: `mcp__abs__qual_analysis` (semgrep + pattern review)
- Playwright async: `mcp__abs__ask_kimi`
- Mutation config: `mcp__abs__ask_gptoss`
- TR error message: `mcp__abs__ask_qwen32b`
- Patch judge: `mcp__abs__judge_patch`

---

## 8. KESİN YASAK (Q7+Q8+...+Q12 S3 dersleri)

- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- Selective subset ≠ FULL CLEAN
- Spec ship ≠ round ilerletti
- Container 46h+ ≠ live (S2 dersi)
- Pilot/market/outreach gündem dışı

---

## 9. ENV (founder hazır)

- Backend: http://localhost:8000 (infra-backend-1, image rebuild gerekirse her round)
- Frontend dev: http://localhost:3000 (founder bu session'da restart etti, canlı)
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s4_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```

---

## 10. BAŞARI KRİTERİ (Session 4 hedefi)

- L22 → 3/3 FULL CLEAN ⭐ (sweep 3 OAuth + Inngest)
- L25 → 3/3 FULL CLEAN ⭐ (sweep 3 RAG batch + plugin install)
- L26 → 2/3 (30dk Playwright sweep 2)
- L21 → 2/3 (migration roundtrip + JWT edge + Vault rotate idempotency)
- Mutmut 1+ round (cascade module + 5+ surviving mutant fix)
- Backend pytest ≥1610 (şu an 1579, hedef +31)
- 5+ yeni real bug
- Image rebuild gate her round (S3 disiplini devam)

---

## 11. PRIORITY (Session 4 odak)

**HIGH:**
1. L22 sweep 3 — OAuth + Inngest race (data corruption riski)
2. L25 sweep 3 — RAG batch + plugin install 50MB (DoS)
3. L26 sweep 2 — 30dk Playwright + heap snapshot (UX continuity)

**MEDIUM:**
4. Mutmut L1 mutation testing (kalite floor)
5. L21 safe expansion (migration + JWT + Vault rotation idempotency)

**LOW (gerekirse):**
6. Q12 L17-L20 deep round 4-5 (SW cache + multi-failure cascade)

---

## 12. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 5.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 13. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -25  # Session 1+2+3 = 25+ commit
cat artifacts/sprint_q12/master_audit_summary.md
cat artifacts/sprint_q12/session_3_complete.md
cat _agent-tasks/WORKER_Q12_SESSION_4.md
```

Round 26 = L22 sweep 3 (OAuth client_id race)'tan başla. Atomic commit per layer.
Image rebuild + container exec evidence ZORUNLU.

Engelleyici YOK. Brief eksiksiz.
