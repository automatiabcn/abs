# Q12 Session 7 — Inherited Q10/Q11 Advanced + Q12 Deep Extension + L21 Founder Gate

> **Tetikleyici:** Q12 Session 6 — 7 atomic round (R35-R41) shipped. **10/10 Q12 katman FULL CLEAN ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐** (L17-L26). Q12-L20-003 gerçek bug fix (12/12 PASS 4 browser). L26 30dk empirical run heap drift **-9.63 MB**. Backend pytest 1611 → 1633 (+22). 4 deep (L18, L19, L20, L23, L24).
> **Hedef:** Inherited Q10/Q11 advanced fuzz + a11y close + OWASP ZAP active scan + Q12 deep extension (L18 offline impl + L23/L24 sweep 5) + mutmut actual run + L21 founder approval kapanış.
> **Branch:** `feat/sprint-q12-deep-quality` (S1-S6 = 42+ commit shipped)

---

## 0. ⚠️ IMAGE REBUILD GATE (S3+S4+S5+S6 sürekli zafer — devam)

S6 backend round'larında image rebuild evidence yapıldı. Aynı disiplin S7'de DEVAM:
```bash
cd /Users/eneseserkan/Main/abs-server-product
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build backend
docker exec infra-backend-1 test -f /app/<yeni dosya> && echo "IMAGE OK"
```

Round summary'ye `image_rebuilt_at:` + `container_pytest_pass:` zorunlu.

---

## 1. ÖNCELIK — INHERITED Q10/Q11 ADVANCED (HIGH)

### Q10-L4 aria-live deep round 2 — kapanış (S6'da 4/5 PASS)
S6 R40 4/5 PASS. 1 fail var (`q12-r35-r36-r37-r38-r39-r40-failed_test_name`). Round 42'de bu fail'i fix + 5/5 PASS → Q10-L4 deep CLOSED.

```bash
cd core/landing
npx playwright test __tests__/playwright/q10-l4-aria-live-deep.spec.ts --reporter=line
# Failed test'i bul, screen reader pattern'i fix
```

### Q11-L13 Hypothesis fuzz scale-up — 3K → 10K (S6 R39 brief'te 10K, ship'te 3K)
```python
@settings(max_examples=10000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.text(min_size=1, max_size=10000))
def test_chat_completion_no_5xx_arbitrary_input(content):
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": content}]})
    assert r.status_code in (200, 400, 422, 429)
```

3 endpoint × 10K iterasyon = 30K toplam. Cascade router + RAG + workflows.

### Q11-L6 OWASP ZAP active scan (HIÇ yapılmadı)
```bash
docker run --rm --network=host -v $(pwd)/zap-report:/zap/wrk/:rw \
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
  -t http://localhost:8000 -r zap-report.html -I

# Active scan (slower, detects injection, XSS, SSRF):
docker run --rm --network=host ghcr.io/zaproxy/zaproxy:stable zap-full-scan.py \
  -t http://localhost:8000 -r zap-full.html
```

OWASP top 10 + injection + auth bypass attempts. Bulunan HIGH severity'ler için fix + regression test.

---

## 2. Q12 DEEP EXTENSION (MEDIUM)

### L18 SW cache offline impl deep round 5 (S6 vanilla SW + 5 spec)
S6 vanilla SW shipped. Deep round 5: gerçek offline mode test:
- Network kesilince /panel/chat draft local'de tutuluyor mu?
- Network gelince queue'lanmış message'lar otomatik flush oluyor mu?
- Chrome devtools Network tab "Offline" mode + chat send → draft persist + reconnect on online

```ts
test('offline draft persists, flushes on reconnect', async ({ page, context }) => {
  await page.goto('/panel/chat');
  await context.setOffline(true);
  await page.fill('[data-testid="chat-input"]', 'offline draft');
  // Send button should disable + draft saved to IndexedDB
  await context.setOffline(false);
  await page.waitForTimeout(2000);
  // Draft should auto-flush
});
```

### L23 sweep 5 — kalan silent raise hunt
S2-S4 sweep 1-4 ile ~50+ path covered. Sweep 5 = remaining modules:
- `app/api/billing*.py` — Stripe webhook + portal raise sites
- `app/api/marketplace.py` — install flow raise sites
- `app/integrations/oauth_*.py` — OAuth provider error paths
- `app/cascade/*.py` — provider failure paths

```bash
grep -rn "raise " core/backend/app/api/billing app/api/marketplace.py app/integrations/oauth core/backend/app/cascade/ | grep -v emit_event
# Her silent raise için emit_event(action, outcome, reason) ekle
```

### L24 sweep 5 — webhook signature secrets (S2'de defer notu vardı, hala yapılmadı)
- Stripe webhook signature secret leak audit (`stripe.Webhook.construct_event` exception path)
- GitHub webhook HMAC SHA256 verification error path
- Slack signing secret verification (`X-Slack-Signature`)
- Inngest signing key verification

```bash
grep -rn "stripe.Webhook\|construct_event\|github_hmac\|slack_signing" core/backend/app/
# Error path'lerinde secret/signature plaintext leak var mı?
```

### L19 deep round 5 — S6 HIGH bug regression (Q12-L20-003)
S6 R35'te fix shipped. Round 47'de regression pin:
```python
def test_q12_l20_003_chat_sessions_error_tile_appears():
    """503 sessions endpoint → sessions-error-tile mount + retry CTA visible."""
    # ... explicit regression test
```

---

## 3. MUTMUT ACTUAL RUN (LOW — async)

S5'te pivot, S6'da CI yaml ship. S7'de actual local run (founder approval — saatlerce sürer):
```bash
ABS_MUTATION_RUN=1 cd core/backend && ./.venv/bin/mutmut run \
  --paths-to-mutate=app/auth/oauth/server.py --tests-dir=tests/ \
  --runner='./.venv/bin/pytest -x' &
# 16-24min beklenir. Founder onaylarsa local'de 1 module.
```

Surviving mutant'lar için boundary test ekle. Yoksa SKIP commit.

---

## 4. L21 SWEEP 4 — DESTRUCTIVE ACTUAL DRILL (founder approval persistent gate)

S5 R34 spec + S6 R38 SKIP. S7'de yine SKIP veya founder onaylarsa actual:
```bash
ABS_DESTRUCTIVE_DRILL=1 ABS_DRILL_ITERS=3 bash scripts/chaos/destructive_drill.sh
```

**FOUNDER ONAYI ZORUNLU** — onaylanmazsa SKIP commit + L21_destructive_run: SKIPPED — pending founder approval.

---

## 5. ROUND DÖNGÜSÜ

1. Layer pick (öncelik: Q10-L4 close → Q11-L13 10K → OWASP ZAP → L18 offline → L23 sweep 5 → L24 sweep 5)
2. Real bug hunt (spec ship YETERSİZ)
3. **Image rebuild + container exec** (backend dokunulduysa)
4. Fix + atomic commit
5. **Container exec verify** + **dış-curl smoke**
6. Round summary `artifacts/sprint_q12/round_<N>_<layer>.md` — `image_rebuilt_at:` + `container_pytest_pass:` zorunlu
7. master_audit_summary.md canlı güncelle

---

## 6. BAŞLANGIÇ ROUND'LARI

### Round 42 = Q10-L4 aria-live close — 5/5 PASS
S6 R40 fail test'i bul, fix, 5/5 PASS doğrula.

### Round 43 = Q11-L13 Hypothesis 10K iter
3 endpoint × 10K iter = 30K. CI runtime'a dikkat — separate test job veya `@pytest.mark.fuzz`.

### Round 44 = Q11-L6 OWASP ZAP baseline scan
zap-baseline.py + report parse + HIGH bulguları fix.

### Round 45 = Q11-L6 OWASP ZAP active scan (slow, ~30dk)
zap-full-scan.py + active injection rules + HIGH bulguları fix.

### Round 46 = L18 SW offline impl + IndexedDB persistence
Workbox/vanilla offline draft + reconnect flush spec.

### Round 47 = L23 sweep 5 — billing + marketplace + OAuth + cascade silent raises
Per-module emit_event coverage. Atomic commit per module.

### Round 48 = L24 sweep 5 — Stripe + GitHub + Slack + Inngest webhook signature audit
Error path leak audit per integration.

### Round 49 = L19 deep round 5 — Q12-L20-003 regression pin

### Round 50 (founder approval) = L21 destructive ACTUAL or SKIP

### Round 51 (founder approval) = Mutmut local actual or SKIP

---

## 7. DELEGATION ZORUNLU (%70+ MCP)

- Test üretimi: `mcp__abs__write_tests`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Hypothesis fuzz patterns: `mcp__abs__ask_gptoss`
- OWASP ZAP results parse: `mcp__abs__qual_analysis`
- SW offline IndexedDB: `mcp__abs__ask_kimi` (React + IndexedDB)
- A11y aria-live: `mcp__abs__ask_qwen32b`
- Patch judge: `mcp__abs__judge_patch`

---

## 8. KESİN YASAK

- Source ship ≠ production deploy → image rebuild zorunlu
- pytest 100/100 ≠ live → dış-curl + container exec
- Selective subset ≠ FULL CLEAN
- Spec ship ≠ round ilerletti
- L21 destructive + Mutmut actual = founder approval ZORUNLU
- Pilot/market/outreach gündem dışı

---

## 9. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3000 (canlı, L18 offline + Q10-L4 + L26 için)
- ZAP: docker pull ghcr.io/zaproxy/zaproxy:stable — ilk round ZAP image gerekiyor
- Cookie üret:
  ```bash
  curl -sk -c /tmp/q12_s7_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' -o /dev/null -w "%{http_code}\n"
  ```

---

## 10. BAŞARI KRİTERİ (Session 7 hedefi)

- Q10-L4 5/5 PASS (deep CLOSED)
- Q11-L13 fuzz 30K iter (3 endpoint × 10K) shipped
- Q11-L6 OWASP ZAP baseline + active scan reports + HIGH fixes
- L18 SW offline draft + reconnect flush impl
- L23 sweep 5 (billing + marketplace + OAuth + cascade)
- L24 sweep 5 (4 webhook signature audits)
- L19 deep round 5 — Q12-L20-003 regression pin
- Backend pytest ≥1660 (şu an 1633, hedef +27)
- 5+ yeni real bug (özellikle OWASP ZAP'tan beklenir)
- Image rebuild gate her backend round

---

## 11. PRIORITY (Session 7 odak)

**HIGH:**
1. Q10-L4 aria-live close (5/5 PASS — deep CLOSED, S6 R40'ta scenario 4 skip kalmış)
2. Q11-L13 Hypothesis 10K iter scale-up (S6 ship 3K, target 10K)
3. Q11-L6 OWASP ZAP baseline + active scan (HIÇ yapılmadı)
4. **L26 R37 ACTIVE drill** — S6 R37 30dk idle PASS. Active = WebSocket reconnect after backend kill + Caddy restart + SSE drop+resume empirical run

**MEDIUM:**
5. L18 SW offline IndexedDB draft persistence (S6 R36 source + R42 runtime kapandı, offline mode kaldı)
6. L23 sweep 5 — billing + marketplace + OAuth + cascade
7. L24 sweep 5 — webhook signature secret audit
8. L19 deep round 5 — S6 HIGH bug regression pin
9. **fs-scan re-run** — `mcp__abs__fullstack_scan` baseline güncelle, missing modules + gap analysis

**LOW (founder approval):**
10. L21 destructive ACTUAL drill
11. Mutmut local actual run

---

## 12. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 8.

Atomic commit + master_audit_summary canlı state sayesinde resume edilebilir.

---

## 13. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -42
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_7.md
```

Round 42 = Q10-L4 aria-live close (5/5 PASS)'tan başla. Atomic commit per round.
Image rebuild + container exec evidence ZORUNLU.

Engelleyici YOK. Brief eksiksiz.
