# Q12 — Round 15 — L22 race condition deep (setup wizard TOCTOU)

**Tarih:** 2026-05-03
**Layer:** L22 — concurrency / race condition (Q12 Session 2 yeni)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Brief: Concurrent multi-admin same tenant: 2 admin aynı anda settings
update → last-write-wins veya optimistic lock? DB transaction isolation
level. TOCTOU bugs. Distributed lock starvation.

---

## 1. Bulgu — Q12-L22-001 (HIGH installation-phase data corruption)

**Lokasyon:** `core/backend/app/api/setup.py` — 6 step endpoint + lang.

Her step handler şu pattern'i takip ediyordu:

```python
async def step_admin(body: AdminBody) -> Dict[str, Any]:
    state = read_state()                    # ← non-locking JSON read
    _ensure_step(state, 1)                  # ← check
    pwd_hash = bcrypt.hashpw(...)           # ← work, mutate
    admin_credentials_path().write_text(...)
    state["data"]["admin"] = {"email": body.email}
    _persist_env_var("ABS_ADMIN_EMAIL", body.email)
    _advance(state, "admin")                # ← state["current_step"] += 1
    _atomic_write_state(state)              # ← non-locking JSON write
    return {"ok": True, "current_step": state["current_step"]}
```

**Race window** (read_state → _atomic_write_state): mikrosaniye, ama
multi-worker uvicorn'da (Helm `replicaCount > 1` veya `gunicorn -w N`)
deterministic olarak açılır.

**Reprodüksiyon (deterministic threaded test):**

```python
def call(email):
    with TestClient(app) as c:
        barrier.wait()
        r = c.post("/v1/setup/step/admin",
                   json={"email": email, "password": "RacePass2026!"})
        results.append(r.status_code)

t1 = threading.Thread(target=call, args=("alice@l22.test",))
t2 = threading.Thread(target=call, args=("bob@l22.test",))
t1.start(); t2.start(); t1.join(); t2.join()

# Pre-fix: results == [200, 200]      ← BOTH succeeded silently
# Post-fix: sorted(results) == [200, 409]
```

**Live confirmation (pre-fix):** test `git stash` ile fix kaldırıldı,
threaded test çalıştırıldı:

```
AssertionError: Q12-L22-001 REGRESSION (threaded): expected one 200
+ one 409, got [200, 200]. Two-admin race-window is open.
```

**Real-world senaryo:** KOBİ pilot install — co-founder A ve B aynı
URL'i 2 sekmede açıp aynı anda wizard'ı tıklar. Pre-fix: `admin_
credentials.json` whichever was written last (non-deterministic) tutar;
losing co-founder hiçbir hata mesajı almadan login'den lock-out olur.
Daha kötüsü, double-advance bug'ı `current_step` 2 yerine 3'e atlayabilir
(state["completed_steps"] iki kez "admin" içerebilir).

---

## 2. Fix (shipped) — `_state_lock()` context manager

```python
import contextlib, fcntl

def _state_lock_path() -> Path:
    return setup_state_path().with_suffix(".json.lock")

@contextlib.contextmanager
def _state_lock():
    p = _state_lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()
```

`fcntl.LOCK_EX` cross-process lock — multi-worker uvicorn'da farklı
process'ler aynı `setup_state.json.lock` üzerinde queue'lanır. Lock
release dosya kapanışında otomatik garanti.

**Refactor:** 7 endpoint'in `read_state ... _atomic_write_state` blok'u
`with _state_lock():` ile sarıldı:
- `/v1/setup/lang`
- `/v1/setup/step/admin`
- `/v1/setup/step/license`
- `/v1/setup/step/domain`
- `/v1/setup/step/anthropic`
- `/v1/setup/step/providers`
- `/v1/setup/step/test`

`_run_provider_tests()` (await içeriyor) lock altında — test endpoint'i
provider'lar için ping atarken state korunur.

**Reset endpoint** lock altında DEĞİL (dev-only; destructive nuke;
state-mutate değil).

---

## 3. Tests — `core/backend/tests/test_q12_l22_race_setup_wizard.py` (4 test)

```
TestQ12L22SetupWizardRace:
  test_concurrent_step_admin_one_winner       ← async ASGI (passes
                                                even pre-fix due to
                                                sync-I/O serialization
                                                in single-process; pin
                                                contract anyway)
  test_serial_step_admin_second_returns_409   ← _ensure_step regression

TestQ12L22StateLockHelper:
  test_state_lock_provides_exclusive_access   ← 2 OS thread + barrier;
                                                max_inside_count must
                                                always == 1
  test_state_lock_threaded_step_endpoints_one_winner ← TRUE multi-thread
                                                race against TestClient;
                                                FAILS pre-fix [200,200],
                                                PASSES post-fix [200,409]
```

**Sonuç:** 4/4 PASS post-fix · 1/4 FAIL pre-fix (verified via git stash).

---

## 4. Layer state

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| **L21** | **1/3** | fresh-deploy drill (safe variant 3/3 PASS) |
| **L22** | **1/3** | race condition fix (setup wizard TOCTOU + 4/4 PASS) |
| **L23** | **1/3** | observability fix (req_id + emit_event + auth.py 9/9 PASS) |
| **L24** | **1/3** | secret leakage fix (magic_token + Stripe 5/5 PASS) |
| **L25** | **0/3** | pending Round 17 |
| **L26** | **0/3** | pending Round 16 |

---

## 5. Atomic commit

```
fix(q12/L22): Round 15 setup wizard TOCTOU — _state_lock fcntl + 7 endpoints + 4 tests (proven via git stash)
```
