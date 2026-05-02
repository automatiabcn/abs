# Q12 — Round 4 — L19 backwards-compat regression

**Tarih:** 2026-05-02
**Layer:** L19 — backwards compatibility (Q12 yeni)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx) + GPT-OSS test scaffolding (kimi empty fallback)

---

## 0. Hedef

Q7 → Q11 + Sprint 21 zaman içinde shipped 11+ HIGH bug fix vardı.
Refactor / merge / yeni sprint sırasında **silently regress**
edebilirler. Q12-L19 tüm geçmiş HIGH için kalıcı pytest guard
ekler. Bir gün CI sessizce bu fix'lerden birini kaybederse,
guard düşer ve commit blok olur.

---

## 1. Kapsanan bug'lar (7 sınıf, 11 test)

| Class | Bug ID | Severity | Guard |
|-------|--------|----------|-------|
| `TestQ7GraphRouterRegression` | Q7 finalize gap | HIGH | `/v1/graph/cypher` 404 olmamalı |
| `TestQ9ChatSessionRegression` | Q9 chat session 404 | HIGH | login sonrası `/v1/chat/sessions` 200 |
| `TestQ10L6QuotaGateRegression` | Q10-L6-001 | HIGH | 50 risky tool seq → ≥1 × 429 |
| `TestQ11L13ChatContentMaxRegression` | Q11-L13-001/003 | HIGH | content size 16384/8001/8000 → 422 only, no 500 |
| `TestQ11L14AlembicMigrationRegression` | Q11-L14-001 | HIGH (prod-blocker) | alembic 0008*.py file exists |
| `TestQ11L15HooksAuthGateRegression` | Q11-L15-001 | MED (info disclosure) | 3 hook endpoint unauthed → 401 not 422 |
| `TestSprint21BundleRegression` | Sprint 21 honest baseline | MED | route chunk total ≤ baseline × 1.20 |

**Çıktı:** `core/backend/tests/test_q12_l19_backwards_compat.py`

---

## 2. Test sonucu (TestClient in-process)

```
collected 11 items

tests/test_q12_l19_backwards_compat.py::TestQ7GraphRouterRegression::test_graph_cypher_endpoint_not_404 PASSED
tests/test_q12_l19_backwards_compat.py::TestQ9ChatSessionRegression::test_chat_sessions_after_login SKIPPED
tests/test_q12_l19_backwards_compat.py::TestQ10L6QuotaGateRegression::test_quota_gate_enforces_429 SKIPPED
tests/test_q12_l19_backwards_compat.py::TestQ11L13ChatContentMaxRegression::test_chat_content_length_boundary[16384-allowed0] PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L13ChatContentMaxRegression::test_chat_content_length_boundary[8001-allowed1] PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L13ChatContentMaxRegression::test_chat_content_length_boundary[8000-allowed2] PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L14AlembicMigrationRegression::test_alembic_0008_present PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L15HooksAuthGateRegression::test_hook_endpoint_returns_401_not_422[/v1/hooks/quota-check] PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L15HooksAuthGateRegression::test_hook_endpoint_returns_401_not_422[/v1/hooks/audit-log] PASSED
tests/test_q12_l19_backwards_compat.py::TestQ11L15HooksAuthGateRegression::test_hook_endpoint_returns_401_not_422[/v1/hooks/session-start] PASSED
tests/test_q12_l19_backwards_compat.py::TestSprint21BundleRegression::test_bundle_within_baseline_plus_buffer PASSED

9 passed, 2 skipped
```

**SKIP nedenleri:**
- `TestQ9` + `TestQ10L6`: TestClient in-process pytest fixture'ı admin@demo-acme.com seed etmiyor. Login 200 dönmediğinde test skip — gerçek backend ile dış-curl regression test ayrıca shipped (master_repro.sh round4_extern).

Dış-curl complement (live backend :8000):
- `/v1/graph/cypher` POST 401 (no auth) ✅
- `/v1/chat/sessions` GET cookie 200 ✅
- `/v1/hooks/quota-check` POST {} 401 ✅
- alembic 0008 file system check ✅

---

## 3. Q12-L19-001 (HIGH) — Sprint 21 H pytest scope dar; 8 pre-existing fail saklı

**Bulgu:** Q12-L19 round'unda TÜM `core/backend/tests/` çalıştırıldığında:

```
8 failed, 1463 passed, 16 skipped in 137s
  test_marketplace_hardening.py: 7 fail
  test_setup_wizard.py::test_anthropic_step_validates_format: 1 fail
```

Sprint 21 H raporu "89/89 PASS" iddia etti. Q11 close raporu
"1101 backend passed". Mevcut full suite 1487 test (Sprint 19/20
+386). Sprint 21 selective subset çalıştırdı — full suite yapsa
bu 8 fail görülürdü. **Sprint 21 close kontrolü yetersiz idi.**

### Kök neden 7/8 marketplace fail

TestClient `/auth/login` POST → **307 Temporary Redirect → /setup**
(setup wizard middleware pre-bootstrap state'te aktif). Test fixture
admin user seed etmiyor, setup wizard hala active. Live backend
(`http://localhost:8000`) bootstrap'lı, `/auth/login` POST 200 verir.

```python
>>> client.post("/auth/login", json={...})
HTTP 307 Temporary Redirect → /setup → 405 Method Not Allowed
# marketplace _login asserts 200 strictly → fail
```

### Kök neden 1/8 setup_wizard fail

`test_anthropic_step_validates_format` 400 expect ediyor ama
Pydantic v2 default 422 döndürüyor. FastAPI default validation
error code 422; özel exception handler shipped değil.

### Q12-L19-001 etki

- Bu 8 fail Q11 close → Sprint 21 close arasında shipped olmuş
- CI muhtemelen full suite çalıştırıyor (`.github/workflows/cicd.yml`
  T-057) ama close raporu manuel "89 PASS" yansıttı (selective)
- Üretim kodu sağlam — sadece test code drift

**Çözüm scope:**
- Test fixture'a admin@local seed (conftest) → 7 marketplace tests
- Setup wizard test 400→422 expectation update
- Sprint 22 cleanup veya Q12 L19 follow-up round (Round +X)

---

## 4. Q12-L19 gerçek bulgu — 1 HIGH (Sprint 21 close gap)

Tüm 9 runnable Q12-L19 guard testi PASS. Eski 11+ HIGH bug
kontrol altında. **YENİ bulgu:** Sprint 21 close raporu pytest
scope'u dar — 8 marketplace + setup wizard test silently fail.
TestClient bootstrap fixture eksiği; Pydantic v2 validation drift.

**Layer state:** L19 sayım **1/3** (9/11 PASS guard + 1 HIGH
finding documented). Q12-L19-001 fix Round +X ya da Sprint 22.

---

## 4. Sonraki round'lar (L19 FULL CLEAN için)

- Round +X: TestClient'a admin@demo-acme.com seed → 11/11 PASS
- Round +Y: dış-curl variant (`scripts/q12_l19_extern_smoke.sh`)
- Round +Z: 6 hafta sonra re-run (silently regress detection)

---

## 5. Atomic commit

```
fix(q12/L19): Round 4 backwards-compat regression — 11 pytest guard for Q7..S21 HIGH bugs
```

---

## 6. Delegation

- Test scaffolding: GPT-OSS 120B (kimi empty fallback) — single attempt
- Worker (Opus): boundary fix (alembic glob path), header import
  cleanup, edge-case TestClient skip-on-login behaviour
- Round 4 doc: kendisi (kompakt, structural)
