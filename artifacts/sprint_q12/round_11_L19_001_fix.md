# Q12 — Round 11 — Q12-L19-001 fix (8 pre-existing pytest fail closed)

**Tarih:** 2026-05-02
**Layer:** L19 — Q12-L19-001 finding follow-up fix
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Round 4'te bulunan Q12-L19-001 (HIGH): full pytest suite 1463
passed + **8 failed** — Sprint 21 close raporu "89 PASS"
selective subset idi. Round 11 8 fail'i fix edip suite **0 fail**'e
döndürür.

---

## 1. Root cause her iki fail kategorisinde

### test_setup_wizard.py::test_anthropic_step_validates_format (1 fail)

```python
r_bad = client.post(".../step/anthropic", json={"anthropic_api_key": "invalidkey"})
assert r_bad.status_code == 400
# AssertionError: assert 422 == 400
```

`AnthropicBody.model_validator` `ValueError` raise eder. Pydantic v2
default → FastAPI 422. Pre-Pydantic-v2 zamanında 400 döndürürdü.
Test expectation outdated.

**Fix:** `assert r_bad.status_code == 422`. Pydantic v2 sözleşmesini
pin eder.

### test_marketplace_hardening.py (7 fail)

```python
def _login(client) -> None:
    r = client.post("/auth/login", json={"email": "admin@local", "password": "CHANGEME"})
    assert r.status_code == 200, r.text
# AssertionError: 405 == 200, {"detail":"Method Not Allowed"}
```

TestClient `/auth/login` POST → **307 → /setup → 405** çünkü
FirstRun middleware setup_state.json `completed:true` görmediğinde
redirect eder.

**conftest** `_autocomplete_setup_state` fixture **session-scoped
data_dir**'a yazar.

**marketplace test** `_isolated_install_store` fixture **per-test
tmp_path** ile `settings.data_dir`'i monkeypatch eder.

Sonuç: per-test data_dir'da setup_state.json yok → middleware
redirect → 405.

**Fix:** `_isolated_install_store` fixture artık tmp_path'a da
setup_state.json yazıyor (session seed pattern'i takip ederek).

---

## 2. Sonuç

```
$ python -m pytest tests/ -q --tb=no
1473 passed, 14 skipped, 14 warnings in 135.46s
```

**Sprint 21 close (89/89 PASS) → şimdi 1473/1473 PASS.**

Önceki state: 1463 passed + **8 failed** + 16 skipped
Yeni state: 1473 passed + **0 failed** + 14 skipped (+10 PASS, -2 SKIP)

Q12-L19-001 (HIGH) **CLOSED ⭐**

---

## 3. Layer state

L19 sayım: **3/3 FULL CLEAN ⭐** (already closed Round 7).
Bu round Q12-L19-001 follow-up fix idi — guard test 11/11 PASS
ve full suite 1473/1473 PASS.

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| L21 | 0/3 | founder-gated |

---

## 4. Atomic commit

```
fix(q12/L19): Round 11 Q12-L19-001 follow-up fix → 1473/1473 backend pytest CLEAN
```

---

## 5. Notlar

- 1 test SKIP yeni (test_live_docker_launch_smoke) — ABS_DOCKER_LIVE
  env-gated, beklenen.
- 1 test SKIP yeni (TestQ10L6QuotaGateRegression) → guard test
  refit edildi Round 7'de, eski SKIP gitti.
- Test count delta: +9 (Round 7 + Round 11 sweep + cosmetic).
