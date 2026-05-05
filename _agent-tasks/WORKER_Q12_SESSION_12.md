# Q12 Session 12 — REGRESSION TRIAGE (Tek Odak — eşik mühür ÖNCESİ kapatılmalı)

> **🚨 KRİTİK (founder verify, 2026-05-05):**
> S11 worker "MÜHÜRLÜ" iddia etti. Founder host full suite çalıştırdı: **1735 PASS + 3 FAIL + 17 ERROR**. Regression S10'dan beri açık, S11'de hiç kapatılmadı. Worker R91-R95 final acceptance + checklist + docs ship etti ama regression triage'ı ATLATTI.
>
> **Bu Q12-L19-001 (S5) → S10 → S11 dersinin 4. tekrarı.** Memory: `feedback_full_suite_mandatory.md`.
>
> **Tek odak:** 20 fail/error'ü kapatmak. Diğer hiçbir round shipping bu session'da yok.
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD 38b3500)

---

## 0. ⚠️⚠️⚠️ FULL SUITE COMMAND — TEK DOĞRU

```bash
cd /Users/eneseserkan/Main/abs-server-product/core/backend
./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
```

**Beklenen son satır:** `X passed, Y skipped, 0 failed, 0 errors`. Sıfır olmayan fail/error varsa Session bitmesin.

Round summary'ye **ZORUNLU** satır:
```
pytest_full_suite: <X passed> / <Y failed> / <Z errors> / <W skipped>
```

**Selective subset (`pytest tests/test_q12_X.py`) ile rapor yazma. 4. selective subset hatası bu session'da olmasın.**

---

## 1. SOMUT KAPATILACAK 20 BAŞARISIZLIK

### Grup A: `test_secrets_api.py` (3 FAILED)
1. `test_rotate_unknown_key_400` — AssertionError
2. `test_rotate_writes_and_invalidates_cache` — AssertionError
3. `test_status_returns_configured_keys_no_cleartext`

**Hipotez:** R84 pricing refactor sırasında 7 yeni `abs_seat_price_*` env var settings'e eklendi. `secrets_api`'nin module-level cache'i settings dict'ini snapshot'lıyor olabilir → rotate flow bozuk. **Bisect zorunlu:**

```bash
git stash  # untracked tutmak için
git checkout 5b1b6d5  # S9 close
./.venv/bin/python -m pytest tests/test_secrets_api.py -q
# 3 FAIL hala var mı? Hayırsa: 5b1b6d5 → 9c6d05c arası bir commit kırdı.
git bisect start
git bisect bad 9c6d05c
git bisect good 5b1b6d5
git bisect run ./.venv/bin/python -m pytest tests/test_secrets_api.py -q
```

İlk kıran commit'i bul, root cause yaz, atomic fix.

### Grup B: `test_q12_provider_degradation_matrix.py` (7 ERROR)
Tüm 7 senaryo full suite'te ERROR (collection veya fixture seviyesi), standalone PASS.

**Hipotez:** Parametrize fixture global env vars set ediyor → önceki test'lerden state kalıntısı (e.g., `test_secrets_api` failed run sonrası env dirty kaldı). Test isolation eksik.

**Fix pattern:**
```python
@pytest.fixture(autouse=True)
def reset_provider_env(monkeypatch):
    """Q12-S12 — explicit env reset for full-suite isolation."""
    for k in [
        "ABS_ANTHROPIC_API_KEY", "ABS_GROQ_API_KEY", "ABS_GEMINI_API_KEY",
        "ABS_CEREBRAS_API_KEY", "ABS_COHERE_API_KEY", "ABS_CLOUDFLARE_API_KEY",
    ]:
        monkeypatch.delenv(k, raising=False)
    # settings cache invalidate gerekirse:
    from app.config import _reset_settings
    _reset_settings() if "_reset_settings" in dir(__import__("app.config")) else None
```

Eğer settings module-level cache yoksa add it. Test runner first-fixture isolation pattern.

### Grup C: `test_q8_chat.py` (10 ERROR)
- test_chat_sessions_empty_list / create / create_default_title / rename / delete / 404_for_missing
- test_chat_completion_streams_session_text_meta / slash_rag_emits_tool_events / continues_existing_session / rejects_non_user_last_msg

**Hipotez:** R64+R65+R70 RSC split-shell migration `/v1/chat/*` endpoint contract'ında subtle change yaptı. Q8 chat tests pre-RSC contract bekliyor.

**Bisect:**
```bash
git checkout 16f8103  # S7 close (pre-RSC migration tamamlanmadan)
./.venv/bin/python -m pytest tests/test_q8_chat.py -q
# Pre-RSC PASS mi?
git checkout 2b196ed  # R64 (audit RSC migrate)
./.venv/bin/python -m pytest tests/test_q8_chat.py -q
# Bu commit kırdı mı?
```

Endpoint contract diff:
```bash
git diff 16f8103..HEAD -- core/backend/app/api/chat.py core/backend/app/api/admin/audit.py
git diff 16f8103..HEAD -- core/landing/app/panel/chat/ core/landing/app/admin/audit/
```

Atomic fix: ya tests'i yeni contract'a uyacak şekilde update et (eğer RSC değişikliği kasıtlıysa), ya da regression revert.

---

## 2. ROUND DÖNGÜSÜ (regression-only)

1. **Pre-state ölç:** Full suite çalıştır, baseline `1735 / 3 / 17` confirm
2. **Grup seç (A/B/C):** Bisect veya kök sebep tespit
3. **Atomic fix commit:** `fix(q12/regression): <test file> — <root cause + 1-line desc>`
4. **Full suite re-run:** O grup düzeldi, diğerlerinde yeni regression yok
5. **Round summary** `artifacts/sprint_q12/round_<N>_regression_<group>.md`:
   ```
   pytest_full_suite_before: 1735 / 3 / 17
   pytest_full_suite_after:  1738 / 0 / 17  (Grup A kapandı)
   bisect_first_bad_commit: <hash>
   root_cause: <açıklama>
   ```
6. **3 grup tamamlanınca:** final full suite GREEN doğrula (`X passed / 0 failed / 0 errors`)

---

## 3. KESİN YASAK

- **Yeni test yaz / yeni layer ekle: YASAK.** Session 12 = sadece regression triage.
- **Selective subset rapor: YASAK.** Round summary tam komut + tam sayı.
- **Eşik mühür / handoff doc / final acceptance shipping: YASAK** (regression kapanmadan).
- **R91 final acceptance E2E spec ddfdf8c kalır** (silmiyoruz) ama "MÜHÜR" iddiası geri çekildi.
- **`docs/qa/tester_handoff_checklist.md` ve `founder_action_items.md` regression açıkken yanıltıcı** — uygun değişiklik gerekirse R96+ yapılır.
- L21 + Mutmut + DR actual: founder approval yok.
- Pilot/market/outreach gündem dışı.

---

## 4. ROUND BAŞLANGIÇ

### Round 96 = Pre-state ölçüm + Grup A (test_secrets_api 3 fail)
- Full suite: `1735 / 3 fail / 17 error / 14 skip / 3 deselected`
- Grup A bisect → ilk kırma commit'i
- Atomic fix
- Re-run: `1738 / 0 fail / 17 error` (Grup A kapandı)

### Round 97 = Grup B (provider degradation 7 error)
- Fixture isolation
- Atomic fix
- Re-run: `1745 / 0 fail / 10 error` (Grup B kapandı)

### Round 98 = Grup C (test_q8_chat 10 error)
- RSC contract diff bisect
- Atomic fix
- Re-run: `1755 / 0 fail / 0 error` ⭐ ALL GREEN

### Round 99 = Final full suite verification + master_audit_summary update
Full suite GREEN evidence, sayı + commit hash.

### Round 100 (regression kapandıktan sonra) = Tester eşik mühür güncelle
`docs/qa/tester_handoff_checklist.md` regression-free state ile günceller, gerçek MÜHÜR yazılır.

---

## 5. DELEGATION ZORUNLU (%70+ MCP)

- Bisect strategy: `mcp__abs__ask_gptoss` (root cause analysis)
- Test isolation pattern: `mcp__abs__ask_kimi` (pytest monkeypatch + fixture)
- RSC contract diff: `mcp__abs__code_review tier=standard`
- Patch judge per fix: `mcp__abs__judge_patch`

---

## 6. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3457 (worker spawn, hung self-restart yetkilisin)
- Pytest komut TEK doğru (Bölüm 0)

---

## 7. BAŞARI KRİTERİ

- **Full suite GREEN:** `X passed / 0 failed / 0 errors` (X≥1755 beklenir)
- 3 grup root cause + atomic fix shipped + bisect commit hash dokümante
- Selective subset rapor YOK — tüm round summary'lerde tam komut
- master_audit_summary S12 entry: regression close-out evidence

Bu session sonunda eşik MÜHÜRLÜ olabilir (regression kapandıktan sonra R100 update).

---

## 8. PRIORITY (Session 12)

**HIGH — TEK ODAK:**
1. R96 Grup A test_secrets_api 3 FAIL fix
2. R97 Grup B test_q12_provider_degradation_matrix 7 ERROR fix
3. R98 Grup C test_q8_chat 10 ERROR fix
4. R99 Full suite GREEN verification

**MEDIUM (regression kapandıktan sonra):**
5. R100 Tester eşik mühür dokümanı güncelle (regression-free state)

**LOW (founder approval — yine SKIP):**
6. L21 destructive — 8/8 SKIP
7. Mutmut local — 7/7 SKIP

---

## 9. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 13.

**Bu session sonunda full suite GREEN olmadan rapor yazma. "MÜHÜRLÜ" iddiası ANCAK 0 fail + 0 error sonrası.**

---

## 10. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -5
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_12.md

# REGRESSION DIAGNOSIS BAŞLANGIÇ:
cd core/backend && ./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py 2>&1 | grep -E "FAILED|ERROR|passed" | head -25
# Beklenen: 1735 passed, 3 failed, 17 errors, 14 skipped, 3 deselected
```

Round 96 = Grup A (test_secrets_api) bisect + fix'ten başla. 3 grup × atomic commit. Full suite GREEN olmadan Session bitmesin.

Engelleyici YOK. Brief eksiksiz. **Bu session = regression close-out, başka hiçbir iş yok.**
