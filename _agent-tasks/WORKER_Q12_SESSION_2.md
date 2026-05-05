# Q12 Session 2 — Layer Genişletme + Derin Regresyon

> **Tetikleyici:** Q12 Session 1 — 4/5 yeni layer FULL CLEAN (L17-L20), 1 HIGH + 4 MED + 2 LOW bug shipped, Sprint 21 raporu yanıltıcılık tespit edildi (1463 PASS+8 hidden FAIL → 1473/1473 fixed).
> **Hedef:** Yeni 5 layer (L22-L26) + Q12 layer 4+ deep regression + L21 safe expansion + inherited Q10/Q11 mutation testing.
> **Branch:** `feat/sprint-q12-deep-quality` (Session 1 üzerinde devam)

---

## 0. Mevcut State (Session 1 sonu)

**Layer matrix:**
- L17 bundle break-even validator: **3/3 ⭐ FULL CLEAN** (CI gate shipped)
- L18 cold-cache LCP: **3/3 ⭐ FULL CLEAN** (CDP real throttle methodology)
- L19 backwards compatibility: **3/3 ⭐ FULL CLEAN** (1473/1473 backend pytest)
- L20 chaos engineering: **3/3 ⭐ FULL CLEAN** (chat redirect:"error" production fix)
- L21 fresh deploy drill: 1/3 (safe variant, destructive variant founder-gated)
- L1-L16 inherited: Q11 close'da 3/3 (rotation pending, Q12'de derinleştirme)

**Test inventory:**
- Backend pytest: 1473/1473 PASS
- Frontend Playwright: 152+ senaryo (Q10 + Q11 + Q12 yeni 30)
- node:test unit: 9 PASS (validate_bundle_split)
- CI gates: ci_bundle_split_gate.js shipped

**Real bugs Session 1:**
- Q12-L17-001 MED — Bundle decision policy LCP-position guard
- Q12-L18-001 MED — Cold-cache + warm-network throttle fidelity gap
- Q12-L18-002 LOW — Lighthouse simulated vs CDP methodology
- Q12-L19-001 HIGH — Sprint 21 close report selective subset (8 hidden fail)
- Q12-L20-001 MED — Chat 307 redirect-loop guard
- Q12-L20-002 LOW — `next start` + `output:"standalone"` uyumsuz

---

## 1. YENİ LAYER'LAR (Q12 Session 2 — 5 yeni boyut)

| # | Layer | Hedef | Tool/yöntem |
|---|-------|-------|-------------|
| **L22** | **race condition deep** | Concurrent multi-admin same tenant: 2 admin aynı anda settings update → last-write-wins veya optimistic lock? DB transaction isolation level (READ COMMITTED vs REPEATABLE READ). TOCTOU bugs (check-then-act). Distributed lock starvation. | pytest-xdist + asyncio + threading.Barrier + SQLAlchemy isolation_level explicit |
| **L23** | **observability gap** | Her error path traceable mi? Structured log (request_id, tenant_id, user_id, action, outcome). Metric counter consistency (cascade routing log vs metric vs DB record). OpenTelemetry trace spans her endpoint. | grep -r "raise " core/backend/ + log assertion + metric query |
| **L24** | **secret/sensitive leakage scan** | API key in error message? Password hash in response? JWT in URL query? Vault secret in audit log? Bu KRİTİK — production'da müşteri verisi sızdıracak path var mı? | semgrep custom rules + manual response inspection + log diff |
| **L25** | **boundary payload** | RAG ingest 25MB limit (worker iddia ediyor) gerçekten zorlanıyor mu? Chat session 1000 mesaj? Workflow 100 node? Plugin install 50MB? Max upload + max DB row + max API response. | Hypothesis property test + boundary fixtures |
| **L26** | **long-running session** | 24h idle browser sekmesi. Token refresh (JWT exp+refresh path). WebSocket reconnect. Idle cleanup. Memory leak (chrome devtools heap snapshot 0/15dk/1h/8h/24h). | Playwright long-poll + chromium devtools protocol |

---

## 2. INHERITED Q10/Q11 LAYER DEEP STRESS (mutation testing + advanced fuzz)

| # | Inherited layer | Q12 Session 2 derinleştirme |
|---|-----------------|------------------------------|
| L1 | unit coverage | **mutmut mutation testing** — her function için 1 char değişiklikle hala PASS oluyor mu? Dead test detection. |
| L2 | integration | RAG concurrent ingest 10 paralel + cascade chain 100 paralel race |
| L3 | e2e theme | 4 viewport × 2 tema × 15 sayfa = 120 senaryo full matrix |
| L4 | a11y | Manual screen reader script (NVDA/VoiceOver simulation via aria announcements) |
| L6 | security | OWASP ZAP active scan (passive + active rules) |
| L9 | graceful | DB-locked + disk-full + Redis-down combinations (cascade failures) |
| L13 | fuzz | Hypothesis 10000 iter chat completions + RAG queries + workflow synthesize |

---

## 3. Q12 LAYER 4+ DEEP REGRESSION (mevcut 3/3 → 4-5/3 stress)

| Layer | 4. round derinleştirme |
|-------|------------------------|
| L17 break-even | Tüm Q11+Q12 dynamic import'ları formülle re-evaluate. Break-even ≥ 530ms olanları flag. |
| L18 cold-cache | Service Worker cache strategies (cache-first / network-first / stale-while-revalidate) for 5 farklı route group. |
| L19 backwards compat | Q7→Q8→Q9→Q10→Q11→Sprint21→Q12 her HIGH bug için **explicit regression test** dosyada. |
| L20 chaos | Multi-failure: backend kill + DB lock simultaneous → cascade UI behavior. |

---

## 4. L21 SAFE EXPANSION (destructive olmadan)

L21 destructive drill founder-gated. Bu arada SAFE variant'ları genişlet:
- Application-layer drill (Session 1'de yapıldı, devam et)
- Migration-only drill: yeni alembic stamp + downgrade -1 + upgrade head 10 round (idempotent doğrula)
- Setup wizard 6-step state machine: her step'te restart + resume → completed:true terminal state aynı mı?
- License JWT expiry edge case: now-1sn / now+0sn / now+1sn / now+24h
- Vault secret rotation: yeni key + decrypt old + re-encrypt new

---

## 5. ROUND DÖNGÜSÜ (Session 1 ile aynı format)

1. Layer pick (round N % 21 rotation, ama Q12 yeni 5 öncelikli + inherited deep round'lar arası)
2. Real bug hunt (spec ship YETERSİZ)
3. Fix + atomic commit (`fix(q12/L<n>): Round <N> Q12-L<n>-<seq>`)
4. Verify (Q10/Q11/Q12 + Sprint 21 regression yok)
5. Round summary (`artifacts/sprint_q12/round_<N>_<layer>.md`)
6. master_audit_summary.md canlı güncelle

---

## 6. BAŞLANGIÇ ROUND'LARI (öncelik sırası)

### Round 13 = L23 observability gap (HIGH IMPACT)
Her error path traceable mi sorgu:
```bash
grep -rn "raise HTTPException\|raise ValueError\|raise PermissionError" core/backend/app/ | wc -l
# Expected: ~150-300 raise sites
# Her biri için: log emitted? metric incremented? trace span?
```

Backend her endpoint:
1. request_id generated (UUID)
2. tenant_id + user_id from JWT logged
3. action + outcome structured log
4. metric counter (success/failure)
5. OpenTelemetry span (eğer enabled)

Bulgu beklenen: 5-20 endpoint'te eksik logging path. Atomic commit per finding.

### Round 14 = L24 secret leakage scan (CRITICAL — security)
```bash
# Semgrep custom rules
semgrep --config=p/secrets --config=p/owasp-top-ten core/backend/

# Manual: error response inspection
curl -X POST http://localhost:8000/auth/login -d '{"email":"x","password":"y"}'
# Beklenen: "credentials_invalid" - NOT "password hash mismatch: bcrypt$2b$..."

# Log diff:
docker logs infra-backend-1 2>&1 | grep -iE "(password|api_key|secret|token|jwt)" | head -20
# Hiçbir secret plaintext olmamalı
```

### Round 15 = L22 race condition (concurrency)
Pytest concurrent execution:
```python
async def test_concurrent_settings_update_last_write_wins():
    """2 admin same tenant, simultaneous PATCH /v1/admin/settings."""
    barrier = asyncio.Barrier(2)
    async def update(value):
        await barrier.wait()
        return await client.patch("/v1/admin/settings", json={"tenant_name": value})
    
    results = await asyncio.gather(update("A"), update("B"))
    # Both 200 OR one 200 + one 409 (optimistic lock)
    # NOT one silent overwrite without warning
```

### Round 16 = L26 long-running session
```ts
test('24h browser tab idle survives', async ({ page, context }) => {
  await page.goto('/panel/chat');
  await page.evaluate(() => window.scrollTo(0, 0));
  
  // Simulate 24h idle (compress to 30s test)
  await page.waitForTimeout(30_000);
  
  // Token should auto-refresh, no "unauthorized" toast
  const status = await page.evaluate(() => fetch('/v1/chat/sessions').then(r => r.status));
  expect(status).toBe(200);
});
```

### Round 17 = L25 boundary payload
```python
def test_rag_ingest_25mb_boundary():
    big_doc = "a" * (25 * 1024 * 1024)  # 25MB
    response = client.post("/v1/rag/ingest", json={"text": big_doc})
    assert response.status_code in (200, 413)  # success or "too large"
    # NOT 500 OOM
```

### Round 18+ rotation:
L1 mutation testing → L9 chaos combinations → L17/L18/L19/L20 deep round 4/5 → L22-L26 sweep 2

---

## 7. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Race condition analiz: `mcp__abs__ask_gptoss` (deadlock detection, isolation reasoning)
- Secret leakage scan: `mcp__abs__qual_analysis` (semgrep + manual review zincir)
- Long-running session pattern: `mcp__abs__ask_kimi` (Playwright async patterns)
- Mutation testing: `mcp__abs__ask_gptoss` (mutmut config + dead test detection)
- TR error message: `mcp__abs__ask_qwen32b`
- Patch judge: `mcp__abs__judge_patch` (AST %60 + LLM %40)

---

## 8. KESİN YASAK (Q7+Q8+Q9+Q10+Q11+Sprint21+Q12 Session 1 ders)

- **Source ship ≠ production deploy** (image rebuild backend dokunulmuşsa)
- **pytest 100/100 ≠ live** (dış-curl + container exec + full test suite)
- **Selective test subset rapor ≠ FULL CLEAN** (Q12-L19-001 dersi — Sprint 21'de 8 hidden fail vardı)
- **Spec ship ≠ round ilerletti** (headless run + gerçek bulgu)
- **Bundle byte ≠ LCP** (network-bound → break-even formülü)
- **Lighthouse simulated ≠ real throttle** (CDP real throttle methodology)
- **Pilot/market/outreach gündem dışı** — sadece teknik kalite

---

## 9. ENV (founder hazır)

- Frontend dev: http://localhost:3000
- Frontend prod: cd core/landing && npm run build && npx next start -p 3458
- Backend: http://localhost:8000
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s2_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```

---

## 10. BAŞARI KRİTERİ (Q12 Session 2 hedefi)

- L22-L26 (5 yeni layer) × en az 1/3 her biri (yani 5+ round real bug hunt)
- Q12 L17-L20 her biri 4+/5+ deep regression round
- Inherited Q10/Q11 mutation testing 1+ round (L1 mutmut)
- L21 safe variant 2/3'e
- Backend pytest ≥1500 (şu an 1473)
- Frontend e2e ≥180 senaryo (şu an 152)
- 5+ yeni real bug (özellikle L23 observability + L24 secret leakage'dan beklenir)

---

## 11. PRIORITY (Session 2'de odak)

**HIGH PRIORITY:**
1. **L24 secret leakage** — production müşteri verisi sızdırma path'i KRİTİK (security)
2. **L23 observability** — incident response için error path traceability ZORUNLU (operability)
3. **L22 race condition** — multi-admin concurrent operasyonlarda data corruption riski (correctness)

**MEDIUM PRIORITY:**
4. L25 boundary payload (DoS resilience)
5. L26 long-running session (UX continuity)

**LOW PRIORITY (gerekiyorsa):**
6. Q12 L17-L20 deep round 4-5
7. Inherited mutation testing
8. L21 safe variant expansion

---

## 12. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 3 brief.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 13. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
cat artifacts/sprint_q12/master_audit_summary.md  # current state
git log --oneline -15  # Session 1'in 11 commit'i + Sprint21'in commit'leri görünür
```

Round 13 = L23 observability gap'tan başla. Atomic commit per finding.

Engelleyici YOK. Brief eksiksiz.
