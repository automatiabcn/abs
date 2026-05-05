# Q12 Session 3 — Layer Tamamlama + Inherited Deep + Image Rebuild Discipline

> **Tetikleyici:** Q12 Session 2 — 7 round (R13-R19) shipped. L23 3/3 FULL CLEAN ⭐. 5 yeni layer (L22-L26) en az 1/3. 4 HIGH bug (L23-001, L24-001, L22-001, L25-001) + 4 MED + 1 LOW + 2 follow-up. Backend pytest 1473 → 1527 (+54). **Founder verify'da image rebuild gap tespit edildi.**
> **Hedef:** L22/L24/L25/L26 her birini 2/3 + 3/3'e götür. L23 sweep 4 (kalan 4 dosya 31 raise site). Inherited Q10/Q11 mutation testing. Q12 L17-L20 deep round 4-5.
> **Branch:** `feat/sprint-q12-deep-quality` (Session 1+2 üzerinde devam)

---

## 0. ⚠️ KRITIK — IMAGE REBUILD GATE

**Q7 + Q8 + Session 2 ÜÇÜNCÜ TEKRAR — backend kaynak değişikliği yapıp image rebuild ETMEDIN.** Founder Session 2 sonu verify'da:
- `docker exec infra-backend-1 test -f /app/app/middleware/request_id.py` → **MISSING**
- `docker exec infra-backend-1 test -f /app/app/observability/audit.py` → **MISSING**
- Container 46 saatlik (Session 2 7 commit shipped, hiçbiri canlı değildi)
- `tests/test_q12_l22_*.py` container'da yok (yeni test dosyaları image'a girmedi)

**Bu sefer:** her round'da backend kaynak değişikliği varsa **commit'ten ÖNCE image rebuild ZORUNLU**:
```bash
cd /Users/eneseserkan/Main/abs-server-product
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend
# Sonra dış-curl + container exec doğrulama:
docker exec infra-backend-1 test -f /app/app/<yeni dosya>.py && echo "IMAGE OK"
docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"
curl -sk http://localhost:8000/<yeni endpoint> | head -5
```

Round summary'ye `image_rebuilt_at: <timestamp>` + `container_pytest_pass: <count>` satırlarını ekle. Eğer image rebuild yoksa round **NOT shipped** sayılır.

---

## 1. ÖNCELIK — L22/L24/L25/L26 SWEEP 2 + 3 (HIGH)

### L23 sweep 4 — kalan 4 dosya 31 silent raise site
Founder verified:
```
app/api/setup.py        — 0 emit_event coverage
app/api/admin/auth.py   — 0 emit_event coverage
app/api/smart_link.py   — 0 emit_event coverage
app/api/beta_admin.py   — 0 emit_event coverage
TOPLAM: 31 raise site, 0/31 audit log
```

L23 zaten 3/3 FULL CLEAN ama **production'da kalan 31 silent path = incident response gözü kapalı**. Sweep 4 bunu bitirmeli. Her dosya ayrı atomic commit.

### L24 sweep 2 — webhook signature secrets
- Stripe webhook signature secret leak audit (stripe.Webhook.construct_event hata mesajı)
- GitHub webhook HMAC SHA256 verification error path
- Slack signing secret verification (`X-Slack-Signature`)
- Inngest signing key verification

```bash
# Tarama:
grep -rn "webhook" core/backend/app/ | grep -iE "(stripe|github|slack|inngest)"
# Her birinde error path'te secret/HMAC plaintext sızdı mı?
```

### L22 sweep 2 — concurrent operasyon race condition
- **Vault rotate race**: 2 admin aynı anda `/v1/admin/vault/rotate` → key corruption?
- **OAuth client registration**: 2 admin aynı `client_id` create → duplicate or 409?
- **Inngest worker idempotency**: aynı event 3 kez fire → 1 kez execute (dedup key)?
- **Cascade routing race**: 100 paralel chat req → routing decision race condition?

### L25 sweep 2 — boundary payload caps (declared yok)
- Workflow nodes count cap: synthesize 100 node → memory + execution time?
- Chat session msg cap: 1000 mesaj → token cost + context window aşımı?
- Plugin install 50MB cap: marketplace install body header `Content-Length` enforce?
- RAG ingest BATCH 100 doc paralel → DoS resilience?

### L26 sweep 2 — long-running session real
Session 2'de typed exceptions yapıldı ama **gerçek 24h test yok**. Sweep 2'de:
- Playwright `test.slow()` + `test.setTimeout(30 * 60 * 1000)` — 30dk gerçek idle
- Chromium DevTools Protocol heap snapshot 0/15dk/30dk fark
- WebSocket reconnect drill (chat SSE + workflow Inngest connection drop+resume)
- Token auto-refresh visible mi (axios interceptor 401 → refresh → retry)?

---

## 2. INHERITED Q10/Q11 — MUTATION TESTING (MEDIUM)

L1 unit coverage `mutmut` ile mutation testing. Hedef: dead test detection.

```bash
cd core/backend
pip install mutmut
mutmut run --paths-to-mutate=app/cascade/ --tests-dir=tests/
mutmut results | head -20
# Beklenen: 5-20 surviving mutant (test'ler boundary case'i yakalamıyor)
```

Sadece bir-iki module için yap (cascade/, providers/) — full repo overkill. Surviving mutant başına 1 yeni test ekle.

---

## 3. Q12 L17-L20 DEEP ROUND 4-5

| Layer | 4-5. round derinleştirme |
|-------|--------------------------|
| L17 break-even | Q12 yeni dynamic import'ları (lazy load chat client, marketplace explorer) re-evaluate. |
| L18 cold-cache | **Service Worker cache strategies** for /panel/chat (cache-first), /panel/dashboard (network-first), /panel/rag (stale-while-revalidate). Implement PRP'sini ship. |
| L19 backwards compat | Q12 Session 2 HIGH bug (Q12-L22-001, Q12-L24-001, Q12-L25-001) için explicit regression test dosyada. |
| L20 chaos | **Multi-failure simultaneous**: backend kill + DB lock + Redis down → cascade UI graceful? |

---

## 4. ROUND DÖNGÜSÜ

1. Layer pick (öncelik: L23 sweep 4 → L24 sweep 2 → L22 sweep 2 → L25 sweep 2 → L26 sweep 2)
2. Real bug hunt (spec ship YETERSİZ, gerçek bulgu zorunlu)
3. **Image rebuild** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** (`docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/<yeni>.py -q"`)
6. **Dış-curl smoke** (`curl -sk http://localhost:8000/<endpoint>`)
7. Round summary `artifacts/sprint_q12/round_<N>_<layer>.md`
8. master_audit_summary.md canlı güncelle

---

## 5. BAŞLANGIÇ ROUND'LARI

### Round 20 = L23 sweep 4 (setup.py + admin/auth.py)
```bash
grep -n "raise " core/backend/app/api/setup.py
grep -n "raise " core/backend/app/api/admin/auth.py
# Her raise için: emit_event(action=..., outcome=..., reason=...)
```

### Round 21 = L23 sweep 4 (smart_link.py + beta_admin.py)
```bash
grep -n "raise " core/backend/app/api/smart_link.py
grep -n "raise " core/backend/app/api/beta_admin.py
# Sweep 4 tamamlanır → L23 4/3 deep
```

### Round 22 = L24 sweep 2 (Stripe webhook secret)
```bash
grep -rn "stripe.Webhook" core/backend/app/
grep -rn "construct_event" core/backend/app/
# Error path'te webhook_secret veya signature plaintext leak var mı?
```

### Round 23 = L22 sweep 2 (Vault rotate race)
```python
async def test_concurrent_vault_rotate():
    barrier = asyncio.Barrier(2)
    async def rotate(actor):
        await barrier.wait()
        return await client.post("/v1/admin/vault/rotate", headers={"X-Admin-Actor": actor})
    a, b = await asyncio.gather(rotate("A"), rotate("B"))
    # Beklenen: 1× 200 + 1× 409 (lock). NOT iki 200 (key corruption riski).
```

### Round 24 = L25 sweep 2 (workflow nodes 100 cap)
```python
def test_workflow_synthesize_100_node_cap():
    body = {"prompt": "x" * 1000, "max_nodes": 100}
    r = client.post("/v1/workflow/synthesize", json=body)
    assert r.status_code in (200, 413, 422)  # success or capped
    # 500 OOM yasak.
```

### Round 25 = L26 sweep 2 (30dk Playwright slow test)
```ts
test('30dk panel chat tab idle survives', async ({ page }) => {
  test.slow();
  test.setTimeout(35 * 60 * 1000);
  await page.goto('/panel/chat');
  await page.waitForTimeout(30 * 60 * 1000);
  // Token auto-refresh, no auth redirect, send message still works
  const status = await page.evaluate(() => fetch('/v1/chat/sessions').then(r => r.status));
  expect(status).toBe(200);
});
```

### Round 26 = mutmut L1 mutation testing
### Round 27+ rotation: L17/L18/L19/L20 deep round 4-5

---

## 6. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Race condition reasoning: `mcp__abs__ask_gptoss` (deadlock detection)
- Webhook secret leakage: `mcp__abs__qual_analysis` (semgrep + manual review zincir)
- Long-running session pattern: `mcp__abs__ask_kimi` (Playwright async patterns)
- Mutation testing config: `mcp__abs__ask_gptoss` (mutmut + dead test detection)
- TR error message: `mcp__abs__ask_qwen32b`
- Patch judge: `mcp__abs__judge_patch`

---

## 7. KESİN YASAK (Q7+Q8+Q9+Q10+Q11+Sprint21+Q12 S1+S2 ÖĞRENİLEN ders)

- **Source ship ≠ production deploy** → image rebuild backend dokunulmuşsa **ZORUNLU**
- **pytest 100/100 ≠ live** → dış-curl + container exec + full test suite
- **Selective test subset rapor ≠ FULL CLEAN** → Q12-L19-001 dersi
- **Spec ship ≠ round ilerletti** → headless run + gerçek bulgu
- **Bundle byte ≠ LCP** → network-bound break-even formülü
- **Lighthouse simulated ≠ real throttle** → CDP real throttle
- **Container 46 saatlik ≠ live** → her round image rebuild + container exec verify (Session 2 dersi)
- **Pilot/market/outreach gündem dışı** → sadece teknik kalite

---

## 8. ENV (founder hazır)

- Backend: http://localhost:8000 (infra-backend-1, image rebuild gerekirse Session 3'te yapılacak)
- Frontend dev: http://localhost:3000
- Frontend prod: `cd core/landing && npm run build && npx next start -p 3458`
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s3_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```
- Image rebuild: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend`

---

## 9. BAŞARI KRİTERİ (Q12 Session 3 hedefi)

- L22/L24/L25/L26 her biri 2/3 (sweep 2 ship) — 4 layer
- L22 veya L24 veya L25'ten en az birini 3/3 FULL CLEAN
- L23 sweep 4 → 4/3 deep (kalan 31 raise site)
- Q12 L17-L20'den en az birini deep round 4 (multi-failure veya SW cache)
- Inherited mutation testing 1+ round (mutmut surviving mutant report)
- Backend pytest ≥1560 (şu an 1527, hedef +33)
- 5+ yeni real bug
- **Her round: image rebuild + container exec + dış-curl evidence** (round_<N>.md'de zorunlu)

---

## 10. PRIORITY (Session 3'te odak sırası)

**HIGH:**
1. L23 sweep 4 (4 dosya, 31 raise site — production incident response gap)
2. L24 sweep 2 (webhook secret leakage — security)
3. L22 sweep 2 (vault rotate + OAuth + Inngest race — data corruption)

**MEDIUM:**
4. L25 sweep 2 (boundary payload caps — DoS)
5. L26 sweep 2 (24h gerçek Playwright — UX continuity)
6. L23 sweep 5 → 5/3 deep (mevcut sweep 4'ten artı dosya çıkarsa)

**LOW (gerekirse):**
7. Inherited Q10/Q11 mutation testing
8. Q12 L17-L20 deep round 4 (SW cache strategies veya multi-failure cascade)

---

## 11. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 4 brief.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 12. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -25  # Session 1+2 19 commit
cat artifacts/sprint_q12/master_audit_summary.md
cat artifacts/sprint_q12/session_2_complete.md
ls _agent-tasks/WORKER_Q12_SESSION_3.md
```

Round 20 = L23 sweep 4 (setup.py + admin/auth.py)'tan başla. Atomic commit per file. Image rebuild + container exec evidence zorunlu.

Engelleyici YOK. Brief eksiksiz.
