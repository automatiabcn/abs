# Q12 — Round 8 — L17 sweep 3 (validator unit tests + CI gate)

**Tarih:** 2026-05-02
**Layer:** L17 — bundle break-even validator 3rd sweep
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Round 1'de validator scripti shipped (`scripts/validate_bundle_split.js`).
Round 6'da rerun PASS. Round 8'de **3rd sweep**: validator
fonksiyonu için node:test unit suite + CI gate (REVERT verdict
varsa workflow fail).

---

## 1. Shipped

### 1.1 `scripts/__tests__/validate_bundle_split.test.js`

9 unit test, node:test framework (zero deps):

| # | Test | Kapsam |
|---|------|--------|
| 1 | Negative delta when bytes save dominates | Slow 3G boundary |
| 2 | Positive delta when RTT dominates (zero bytes) | Faz D analog |
| 3 | Cascade RTT linear penalty | Faz C 2-step boundary |
| 4 | Linear scaling savedBytes ↔ downloadMs | formula sanity |
| 5 | Sprint 21 evaluate produces 12 rows (4 dec × 3 profiles) | matrix shape |
| 6 | Faz B /panel/quota fiber NEUTRAL boundary | regression pin |
| 7 | Faz D NON_LCP under all profiles | non-LCP semantic |
| 8 | NETWORK_PROFILES.slow3G constants | profile pinning |
| 9 | No REVERT verdict on Sprint 21 set | regression guard |

```
$ node --test scripts/__tests__/validate_bundle_split.test.js
# tests 9
# pass 9
# fail 0
# duration_ms 37.46
```

### 1.2 `scripts/ci_bundle_split_gate.js`

CI wrapper. REVERT verdict gördüğünde exit code 1, satır listesi
stderr'a basar. Yeni `next/dynamic` shipped olduğunda PR CI
otomatik bayrak çeker.

```bash
$ node scripts/ci_bundle_split_gate.js
Q12-L17 gate: 0 REVERT verdicts across 12 rows. PASS
$ echo $?
0
```

GitHub Actions integration (Sprint 22'de eklenecek workflow step):

```yaml
- name: Q12-L17 bundle break-even gate
  run: node scripts/ci_bundle_split_gate.js
```

---

## 2. Round 8 gerçek bulgu — yok (CLEAN)

Validator fonksiyonu mathematically sound: 4 boundary test +
3 Sprint 21 regression pin + 1 cascade linearity proof PASS.
Sprint 21 4 commit'inde 0 REVERT — KOBİ pilot için CI gate
açık.

**Yan kazanım:** Validator artık bağımsız test edilebilir
(test runner zero deps, < 40ms runtime). Sprint 22 RSC
migration sonrası `SPRINT_21_DECISIONS` array'i `SPRINT_22_RSC_DECISIONS`
ile değiştirilebilir; aynı test harness yeniden kullanılır.

---

## 3. Layer state

L17 sayım: **3/3 FULL CLEAN ⭐**
(Round 1 ship + Round 6 rerun + Round 8 unit tests + CI gate)

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | **bundle break-even validator** + 9 unit test + CI gate |
| L18 | 2/3 | cold-cache LCP |
| **L19** | **3/3 ⭐** | **backwards compat 11/11 PASS** |
| L20 | 2/3 | chaos engineering |
| L21 | 0/3 | fresh deploy — founder approval pending |

**2/5 Q12 yeni layer FULL CLEAN.**

---

## 4. Atomic commit

```
fix(q12/L17): Round 8 sweep 3 — validator unit tests + CI gate → L17 FULL CLEAN
```
