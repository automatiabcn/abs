# Q12 Session 11 — REGRESSION KAPATMA + Tester Teslimat Eşik (eşik mühür ÖNCESİ)

> **🚨 KRİTİK BULGU (founder verify, 2026-05-05):**
> Worker S10 raporu **1790 PASS** iddia etti. Host full suite çalıştırıldığında: **1734 passed + 3 FAILED + 17 ERROR + 14 skipped + 3 deselected**. Bu Q12-L19-001 (Sprint 21 selective subset gap) dersinin TEKRARI. Standalone test PASS ≠ full suite PASS.
>
> **Founder direktifi (2026-05-04):** "test asamalarini yavas yavas bitirecegiz". Eşik mühürleme ÖNCESİ regression KAPATILMALI.
> **Hedef:** Session 11 = regression close-out → 1734+ → tüm full suite GREEN. Sonra final acceptance E2E + tester teslimat eşik mühürleme.
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD 9c6d05c, 95 commit)

---

## 0. ⚠️ ÖNCELİK 1 — REGRESSION KAPATMA (TÜMÜ HIGH)

### 0.1 BACKEND PYTEST FULL SUITE GRÜEN OLMALI
Founder run komutu (worker'ın da bu komutu kullanması zorunlu, **selective subset YASAK**):

```bash
cd /Users/eneseserkan/Main/abs-server-product/core/backend
./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
# Beklenen: 0 failed, 0 errors. PASS sayısı ≥1730.
```

Worker'ın iddia ettiği 1790 + 17 ERROR + 3 FAIL = 1810 collected. Excluded 3 module = 19 extra. Toplam ~1810 - 19 = 1791 host expected. Şu an host: 1734 PASS + 3 FAIL + 17 ERROR = 1754 effective.

### 0.2 BAŞARISIZ TEST KATEGORİLERİ + KÖK SEBEP HİPOTEZLERİ

**A) `test_secrets_api.py` 3 FAILED (HIGH — R84 pricing refactor regression?):**
- `test_rotate_unknown_key_400` — AssertionError
- `test_rotate_writes_and_invalidates_cache`
- `test_status_returns_configured_keys_no_cleartext`

Hipotez: R84 7 yeni env var (`abs_seat_price_*`, `abs_revenue_widget_multiplier`, `abs_price_*`) settings'e eklendi → secrets_api'nin module-level state cache'i bunlardan etkilendi → rotate flow bozuldu.

```bash
git diff 5b1b6d5..HEAD -- core/backend/app/config.py core/backend/app/secrets/ core/backend/app/api/secrets*.py
# settings tarafında side-effect var mı?
```

**B) `test_q12_provider_degradation_matrix.py` 7/7 ERROR (HIGH — R85 fixture state pollution):**
- 7 senaryo full suite'te ERROR, ama standalone PASS (founder doğrulama: 7/7 PASS in 5.85s).

Hipotez: R85 parametrize fixture'ı global env vars'ı set ediyor; önceki test'lerden state kalıntısı var. Test isolation eksik.

```bash
# Test self-contained env reset yap:
@pytest.fixture(autouse=True)
def reset_provider_env(monkeypatch):
    for k in ["ABS_ANTHROPIC_API_KEY", "ABS_GROQ_API_KEY", ...]:
        monkeypatch.delenv(k, raising=False)
```

**C) `test_q8_chat.py` 10 ERROR (HIGH — RSC migration regression):**
- chat sessions list/create/rename/delete/404 + completion + RAG + non-user last msg

Hipotez: R64+R65+R70 RSC split-shell migration `/v1/chat/*` endpoint contract'ında subtle change yaptı; pre-Q8 chat tests broken.

```bash
git diff ba22cd1..HEAD -- core/backend/app/api/chat.py core/landing/app/panel/chat/
# /v1/chat/sessions endpoint imzasında değişiklik var mı?
```

### 0.3 ROUND 91 = REGRESSION TRIAGE
Tüm 20 fail/error'ün her biri için:
1. Standalone test çalıştır → standalone PASS mi?
2. Önceki HEAD'de çalıştır (e.g., S9 close 5b1b6d5)?
3. Bisect: hangi commit ilk break etti?
4. Atomic fix commit + re-run full suite → 0 fail 0 error doğrula

Round 91 atomic commit listesi beklenen:
- `fix(q12/regression-secrets): test_secrets_api 3 fail — <root cause>`
- `fix(q12/regression-degradation): test_q12_provider_degradation_matrix fixture isolation`
- `fix(q12/regression-q8-chat): test_q8_chat.py 10 error — <root cause>`

### 0.4 FULL SUITE GATE (MERGE-BLOCKER)
Round 91+ shipped sonrası `pytest --no-header -q` çalıştır. **3 fail + 17 error → 0 fail + 0 error olmadan Session 11 bitmesin.**

---

## 1. EŞİK MÜHÜR (regression kapanınca, R92+ ile)

Regression kapatılınca aşağıdaki sıraya geç:

### R92 = Final acceptance E2E (combined Playwright, 6 phase)
R78 + R85 + R86 + R87 birleştirilmiş tek senaryo: setup → provider degradation → license → multi-admin → first usage → recovery.

### R93 = `docs/qa/tester_handoff_checklist.md`
Somut PASS evidence + commit hash + Founder Action Items section.

### R94 = `docs/qa/founder_action_items.md`
7 madde: Stripe Price IDs, env vars, license JWT, Cerbos helm, image rebuild, Lighthouse review, tester'a iletim.

### R95 = Documentation final review
README + quickstart + troubleshooting + runbook eksiklerini kapat.

### R96 = Final fs-scan + master_audit_summary close

---

## 2. KESİN YASAK + S5+S9 DERSLER

- **Selective subset rapor → FULL CLEAN sayma** (Q12-L19-001 + S10 dersi). Full suite ZORUNLU.
- "Shipped + test PASS standalone" ≠ "full suite PASS" — aynı pattern S5+S10 (3. tekrar)
- Source ship ≠ production deploy → image rebuild
- L21 + Mutmut + DR actual: founder approval olmadan ÇALIŞTIRILMASIN
- Pricing audit'i yeniden açma — sadece regression sebepli rollback'ler kabul
- Pilot/market/outreach gündem dışı

---

## 3. ROUND DÖNGÜSÜ (regression-first)

1. **Triage:** her fail/error için standalone PASS doğrula + bisect
2. Kök sebep tespit + atomic commit per fail/error grup
3. **Full suite re-run** her commit sonrası (selective YASAK)
4. **Image rebuild + container exec** (backend dokunulduysa)
5. Round summary: hangi test'ler düzeltildi, root cause + bisect commit

---

## 4. DELEGATION ZORUNLU (%70+ MCP)

- Test bisect: `mcp__abs__ask_gptoss` (root cause analysis)
- Fixture isolation pattern: `mcp__abs__ask_kimi` (pytest monkeypatch)
- RSC chat endpoint diff: `mcp__abs__code_review` + `mcp__abs__qual_analysis`
- Patch judge: `mcp__abs__judge_patch`

---

## 5. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3457
- Pytest komut (TEK doğru):
  ```bash
  cd core/backend && ./.venv/bin/python -m pytest --no-header -q \
    --ignore=tests/test_providers.py \
    --ignore=tests/test_q03_real_saas_backends.py \
    --ignore=tests/test_update_channel.py
  ```

---

## 6. BAŞARI KRİTERİ (Session 11)

- **REGRESSION KAPALI: full suite 0 fail + 0 error (≥1750 PASS)**
- Final acceptance E2E PASS (6 phase combined)
- tester_handoff_checklist.md shipped
- founder_action_items.md shipped
- README + 3 doc reviewed
- fs-scan honest 95+ korundu
- Image rebuild + live_path_verified evidence per round

---

## 7. PRIORITY (Session 11)

**HIGH (regression kapanış — eşik MÜHÜR ÖNCESİ ZORUNLU):**
1. R91 Regression triage + fix (test_secrets_api 3 + test_q8_chat 10 + test_q12_provider_degradation 7)
2. **Full suite GREEN: 0 fail + 0 error**

**HIGH (regression kapandıktan sonra eşik mühür):**
3. R92 Final acceptance E2E (6 phase)
4. R93 tester_handoff_checklist.md
5. R94 founder_action_items.md
6. R95 Documentation review
7. R96 Final fs-scan close

**LOW (founder approval):**
8. L21 destructive ACTUAL — 7/7 SKIP
9. Mutmut local actual — 6/6 SKIP

---

## 8. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 12.

**Bu session sonunda ya regression kapanmış olacak (eşik mühür hazır) ya da kapanmamış olursa eşik MÜHÜRLÜ DEĞİL — Session 12'de devam edilir.**

---

## 9. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -90
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_11.md

# Regression diagnosis ile başla:
./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py 2>&1 | grep -E "FAILED|ERROR" | head -25
```

Round 91 = REGRESSION TRIAGE'tan başla. Full suite GREEN olmadan Session 11 bitmesin. Eşik mühür ANCAK regression kapanınca.

Engelleyici YOK. Brief eksiksiz. **Bu session önce regression kapatma, sonra eşik mühürleme.**
