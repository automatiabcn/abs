# Q12 — Round 19 — L23 sweep 3 (me_data_export.py audit coverage)

**Tarih:** 2026-05-03
**Layer:** L23 — observability gap (sweep 3 → FULL CLEAN target)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Round 13 audit ikinci silent offender: `me_data_export.py` 10/10
(GDPR Article 15 — right of access / data portability).

Failure path'leri pre-fix sessiz:

| Senaryo | Endpoint | Status |
|---------|----------|--------|
| Missing Bearer | POST /v1/me/data-export | 401 silent |
| License invalid | aynı | 400/401 silent + str(exc) leak |
| Missing JTI | aynı | 401 silent |
| Job not found | GET /v1/me/data-export/{job_id} | 404 silent |
| Not owner | aynı (cross-license enumeration) | 403 silent |
| Job not found (download) | GET /v1/me/data-export/{job_id}/download | 404 silent |
| Not owner (download) | aynı | 403 silent |
| Not ready | aynı | 409 silent |
| Expired | aynı | 410 silent |
| File missing (server-side issue) | aynı | 404 silent |

Cross-license enumeration örneği: adversary leaked Bearer A ile job_id
B'nin GET'ini denerse 403 alır ama log yok → ops "data export
enumeration attempt" tespit edemez.

---

## 1. Fix (shipped) — emit_event 10 path için

Action taxonomy:
| Action | Reasons |
|--------|---------|
| `me.data_export.auth` | missing_bearer / license_invalid / license_verify_exception / missing_jti |
| `me.data_export.status` | job_not_found / not_owner |
| `me.data_export.download` | job_not_found / not_owner / not_ready / expired / file_missing |

Helper `_verify_bearer_license(authorization, request=None)` `Optional[Request]`
parametresi ile threaded. Tüm endpoint signatures `request: Request`
parametresi alıyor (Header parametre sırasına göre sıralanmış).

### Side fix — Q12-L24 follow-up (MED, sweep 2'ye paralel)

Aynı `f"License verify failed: {exc}"` leak me_data_export.py'da da
vardı. Aynı fix (`license_verify_failed` generic detail + emit_event
internal `error_class`) shipped.

---

## 2. Tests — `core/backend/tests/test_q12_l23_sweep3_me_data_export.py` (4 test)

```
TestQ12L23Sweep3DataExportAuth (2):
  test_missing_bearer_emits_denied         ← 401 + reason="missing_bearer"
  test_invalid_bearer_no_str_exc_leak      ← 400/401 + audit + L24 leak guard

TestQ12L23Sweep3DataExportStatus (1):
  test_job_not_found_emits_denied          ← 404 + reason="job_not_found"

TestQ12L23Sweep3DataExportDownload (1):
  test_download_job_not_found_emits_denied ← 404 + audit
```

**Sonuç:** 4/4 PASS + pre-existing test_029_gdpr_data_export.py 7/7
PASS (backwards compat preserved).

---

## 3. L23 → 3/3 FULL CLEAN ⭐

Sweep 1 (Round 13): RequestIDMiddleware + emit_event helper +
auth.py 5 paths (9/9 tests).

Sweep 2 (Round 18): me_account.py 11 paths (6/6 tests).

Sweep 3 (Round 19): me_data_export.py 10 paths (4/4 tests).

**Toplam:** 26 yeni patched path × emit_event coverage. Bu 3 sweep
en kritik failure path'leri kapatıyor (panel session decode + GDPR
delete + GDPR export). Geriye kalan 4 dosya (setup.py 8/8,
admin/auth.py 8/9, smart_link.py 7/7, beta_admin.py 7/7) ileri
round'larda session 3+ için ayrı deep sweep işleri.

---

## 4. Layer state

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| **L21** | **1/3** | fresh-deploy drill (safe variant 3/3 PASS) |
| **L22** | **1/3** | race condition fix (setup wizard TOCTOU 4/4 PASS) |
| **L23** | **3/3 ⭐** | observability — auth.py + me_account.py + me_data_export.py (3 sweeps, 19/19 tests, 5 layers FULL CLEAN ⭐⭐⭐⭐⭐) |
| **L24** | **1/3** + 2 follow-ups | secret leakage + me_account/me_data_export str(exc) fixes |
| **L25** | **1/3** | boundary payload (marketplace + 14/14 PASS) |
| **L26** | **1/3** | JWT lifecycle hardening (typed exceptions + 9/9 PASS) |

**5 Q12 yeni layer FULL CLEAN ⭐ (L17-L20 + L23) + 5 Q12 NEW Session
2 layer 1/3** (L21, L22, L24, L25, L26).

---

## 5. Atomic commit

```
fix(q12/L23-sweep3): Round 19 me_data_export.py audit coverage — 10 paths emit_event + L24 follow-up + 4/4 tests PASS → L23 3/3 FULL CLEAN ⭐
```
