# Q12 Session 10 — PRODUCTION READINESS — Pricing + Provider + License + Magic-Link

> **Founder direktifi (2026-05-04, devam):** "artik gercekten sistemin hazir oldugundan emin olmaliyiz test asamalarini yavas yavas bitirecegiz"
>
> **Tetikleyici:** Q12 S9 — 8 round (R76-R83) shipped. 2 real bug closed (Cerbos cerbos.env map/list — Caveat #12 production silent drop; Lighthouse nightly abs.local hostname). S9'da yapılmadı: pricing audit, provider degradation matrix, license JWT lifecycle, magic-link multi-admin. Backend pytest 1718 → 1753 (+35). HEAD 5b1b6d5.
> **Hedef:** S9'da kalan 4 production-readiness item'ı bitir + R78 first-customer E2E review + Q9 SKIP item kalıntıları.
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD 5b1b6d5)

---

## 0a. ⚠️ DEV SERVER RESTART YETKİSİ — devam

`/v1/admin/users` 3457 hung'da kill+restart yetkilisin (Bölüm 0a'dan).

## 0. ⚠️ IMAGE REBUILD GATE — devam

Backend dokunulduysa image rebuild + container exec evidence ZORUNLU.

## 0c. ⚠️ "SHIPPED ≠ LIVE" PATTERN UYARISI (S9 dersi — 2 bug)

S9'da 2 bug aynı pattern: **shipped + test PASS gibi gözüktü, gerçek path'te hiç çalışmamıştı.** Q7+Q8 image rebuild dersinin uzun kuzeni:
- Cerbos cerbos.env map → list (helm coalesce silent drop, Caveat #12 hiç enforce edilmedi)
- Lighthouse nightly abs.local hostname (runner resolve etmiyor, log bile yok)

Bu session'da fix shipping yaparken:
- Config değişiklikleri DEPLOY edilmiş canlı yapı'da DOĞRULA (helm get values + kubectl describe)
- Cron job'lar artifact upload + log capture etmeli (silent fail tespit edilebilsin)
- "Test PASS" + "production live" ayrı doğrulamalar — birinin geçmesi diğerini garanti etmez

Round summary'ye `live_path_verified: true|false` + komut not düş.

---

## 1. ÖDEV — S9'DA YAPILMAYANLAR (HIGH)

### 1.1 PRICING AUDIT + EXTRACT (memory uzun süredir defer)
Memory: `project_tester_handoff_plan.md`. Tester'a verilmeden önce repo'da hardcoded fiyat KALMAMALI.

```bash
cd /Users/eneseserkan/Main/abs-server-product
grep -rnE "\\\$[0-9]+|[0-9]+ ?USD|monthly_price_usd" \
  core/backend/app core/landing/app core/landing/components 2>&1 | \
  grep -v "test\|spec\|\.test\.\|fixture\|mock\|cost.*\$0\|approximate\|ollama_first\|free tier\|\$0.30" | \
  head -30
```

Bilinen hardcoded değerler (Session 4'te tespit, hala canlı):
- `core/backend/app/billing_v10/seats.py:35` — `monthly_price_usd=299.0` (self-host)
- `core/backend/app/billing_v10/seats.py:41` — `monthly_price_usd=1196.0` (team-5)
- `core/backend/app/billing_v10/seats.py:47` — `monthly_price_usd=2093.0` (team-10)
- `core/backend/app/mcp/tools/status_tools.py:95` — `price_map = {("self-host", 1): 299, ("team", 5): 1196, ("team", 10): 2093}`
- `core/backend/app/static/admin/index.html:239` — `$${total * 25}/mo` revenue widget multiplier
- `core/backend/app/api/status_page.py:224` — docstring "self-host=$299/12, team-5=$99/seat/mo"
- Email templates (`expiry_warning.html`, `beta_renewal_offer_*.html`) — `$49/yıl maintenance`, `$4,800 → $2,400`

**Extract pattern:**
1. `app/config.py` → `abs_seat_price_self_host: float = 0.0`, `abs_seat_price_team_5: float = 0.0`, `abs_seat_price_team_10: float = 0.0`, `abs_revenue_widget_multiplier: float = 0.0`
2. `billing_v10/seats.py` → `monthly_price_usd=settings.abs_seat_price_self_host` (vb.)
3. `mcp/tools/status_tools.py` → `price_map` settings'ten oluştur
4. `admin/index.html` → backend endpoint `/v1/system/widget_pricing` → fetch + render
5. Email templates → template variable `{{maintenance_price_yearly}}`, `{{annual_offer_strike}}`, `{{annual_offer_price}}` — render context'ten
6. `status_page.py` docstring → kaldır veya nötr ifadeyle değiştir

Default değerler `.env.example`'da örnek olarak yazılır ama kod'da YOK. Müşteri kendi env'inde set eder.

**Tier ID'leri ("self-host", "team-5", "team-10") KALIR** — bunlar SKU id, fiyat değil. Sadece dolar değerleri çıkar.

**Doğrulama:**
```bash
grep -rnE "\\\$[0-9]+|monthly_price_usd ?= ?[0-9]+|price_map ?= ?{" core/backend/app core/landing/app 2>&1 | \
  grep -v "test\|spec\|\.env\.example\|fixture\|mock\|cost.*\$0\|approximate" | wc -l
# Beklenen: 0 (veya tek tek allowlist'le justify edilmiş)
```

### 1.2 PROVIDER DEGRADATION MATRIX 7 SENARYO
Memory: `feedback_provider_degradation_test.md`. Cascade graceful fallback + UI gri/disabled + `quota_status configured:bool`.

```python
# tests/test_q12_provider_degradation_matrix.py
@pytest.mark.parametrize("scenario", [
    ("all_present",       6, 6),  # 6/6 cascade aktif
    ("anthropic_skip",    5, 5),  # 5/6, free path only
    ("groq_missing",      5, 5),  # gri Groq disabled
    ("3_free_missing",    3, 3),  # 3/6
    ("5_free_missing",    1, 1),  # Anthropic only
    ("all_free_missing",  0, 1),  # UI gracefully degraded, only Anthropic
    ("all_invalid",       0, 0),  # UI shows invalid key error
])
def test_provider_degradation_matrix(scenario, expected_active, expected_configured):
    # Set env vars per scenario
    # POST /v1/cascade/route → expected behavior
    # GET /v1/system/quota_status → configured count matches
    pass
```

7 senaryo PASS = degradation hazır.

### 1.3 LICENSE JWT FULL LIFECYCLE (4 boundary + revoke + tamper + 100y guard)
S5 R28'de alembic + JWT boundary spec ship'ti. S10'da E2E lifecycle:

```python
# tests/test_q12_license_full_lifecycle.py
def test_license_now_minus_1s_rejected():
def test_license_now_plus_0s_rejected():
def test_license_now_plus_1s_accepted():
def test_license_now_plus_24h_accepted():
def test_license_revoked_then_reissue_works():
def test_license_tampered_signature_rejected():
def test_license_100y_expiry_warning_logged():  # Q12-L21-003 LOW non-bug pin
```

7 test PASS = JWT lifecycle prod-ready.

### 1.4 MAGIC-LINK MULTI-ADMIN FULL FLOW
S2 R14'te magic_token plaintext leak fix'lendi. S10'da E2E flow:

```python
# tests/test_q12_magic_link_e2e.py
def test_admin_a_signup_magic_link_claim_to_panel():
def test_token_24h_expiry_then_reuse_blocked_401():
def test_admin_a_invites_admin_b_same_tenant():
def test_two_admins_both_active_in_tenant():
def test_admin_a_cross_tenant_block_403():
def test_magic_token_email_does_not_leak_token_in_audit():  # Q12-L24-001 regression
```

6 test PASS = multi-admin signup prod-ready.

### 1.5 R78 FIRST-CUSTOMER 11-STEP E2E REVIEW
R78 d13588c — "first-customer 11-step full-sweep" 3/3 PASS shipped. Brief'imdeki **setup wizard E2E** ile aynı kapsam mı? Doğrula:

```bash
cat core/landing/__tests__/playwright/q12-l29-first-customer-flow.spec.ts | head -60
# Beklenen step'ler: setup → step 1-6 → login → /panel → first chat + RAG + workflow
# Eksikse: ekle. R78 spec'i augment et.
```

---

## 2. R76 + R82 BUG AFTERMATH (LOW)

R76 Cerbos cerbos.env fix shipped — production cluster'da live verify gerekli. Worker DRY-RUN ile fix'ledi, gerçek deploy founder approval gerektirir. **Skip + spec ship + founder approve actual.**

R82 Lighthouse nightly fix shipped — sonraki Cumartesi 02:00 UTC cron'da artifact üretsin → Pazartesi sabah review.

---

## 3. FOUNDER GATE — KARAR ZAMANI HALA AÇIK

L21 destructive ACTUAL drill — 6/6 session SKIP olacak (founder yine devam derse).
Mutmut local actual run — 5/5 session SKIP.

Founder bu session'da onaylarsa actual run, yoksa SKIP commit.

---

## 4. ROUND DÖNGÜSÜ

1. Item pick (öncelik: pricing → provider degradation → license JWT → magic-link → R78 review)
2. Validation: mevcut sistem üzerinde doğrulama, yeni layer DEĞİL
3. Bulgu varsa fix + atomic commit
4. **Image rebuild + container exec** (backend dokunulduysa)
5. **Live path verified** (S9 dersi — config drift / silent fail kontrol)
6. Round summary `artifacts/sprint_q12/round_<N>_<focus>.md`

---

## 5. BAŞLANGIÇ ROUND'LARI

### Round 84 = Pricing audit + extract
6 surface (seats.py + status_tools.py + admin/index.html + status_page.py docstring + 2 email template). Her biri ayrı atomic commit. Sonunda `grep -rnE "\\\$[0-9]+|monthly_price_usd ?= ?[0-9]+"` 0 hardcoded.

### Round 85 = Provider degradation matrix 7 senaryo
7 parametrize test + UI screenshots her senaryoda + quota_status configured:bool.

### Round 86 = License JWT full lifecycle 7 test

### Round 87 = Magic-link multi-admin 6 test

### Round 88 = R78 first-customer E2E review + augment (eksikse)

### Round 89 = R76 Cerbos production live deploy verify (founder approval)

### Round 90 = R82 Lighthouse nightly artifact review (Pazartesi sonrası)

### (Founder approval) = L21 + Mutmut actual

---

## 6. DELEGATION ZORUNLU (%70+ MCP)

- Pricing audit: `mcp__abs__code_review` + `mcp__abs__ask_qwen32b` (env var pattern)
- Provider degradation: `mcp__abs__qual_analysis` + `mcp__abs__quota_status` MCP
- License JWT boundaries: `mcp__abs__ask_gptoss`
- Magic-link flow: `mcp__abs__write_tests` + `mcp__abs__ask_kimi`
- Patch judge: `mcp__abs__judge_patch`

---

## 7. KESİN YASAK

- Yeni test layer ekleme — Session 10 = mevcut sistemi tester teslimat eşiğine yaklaştırma
- Source ship ≠ production deploy → image rebuild zorunlu
- "Shipped + test PASS" ≠ "live path works" — config + cron live verify (S9 dersi)
- L21 + Mutmut + DR actual: founder approval olmadan ÇALIŞTIRILMASIN
- Helm dry-run actual deploy DEĞİL — production cluster'a dokunma
- Pricing audit: tier ID'ler ("self-host", "team-5") KALIR, sadece dolar değerleri çıkar
- Pilot/market/outreach gündem dışı

---

## 8. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3457 (worker spawn, hung self-restart yetkilisin)
- Cookie: admin@demo-acme.com / DemoPass2026!
- Provider keys (test): `.env.test` veya isolated namespace q12-s10-providers

---

## 9. BAŞARI KRİTERİ (Session 10 = tester teslimat eşik close-out)

- Pricing audit: hardcoded $ değer 0 (env var'a taşındı, repo'da grep boş)
- Provider degradation 7/7 senaryo PASS
- License JWT 7 test PASS (4 boundary + revoke + tamper + 100y)
- Magic-link 6 test PASS (signup + claim + cross-tenant block)
- R78 11-step E2E spec review + augment (eksikse)
- R76 Cerbos live verify spec ship (actual deploy founder gate)
- Backend pytest ≥1780 (şu an 1753, hedef +27)
- Image rebuild gate korundu

---

## 10. PRIORITY (Session 10)

**HIGH (tester teslimat eşik close-out):**
1. Pricing audit + extract (6 surface, $ → env var)
2. Provider degradation matrix 7 senaryo
3. License JWT full lifecycle 7 test
4. Magic-link multi-admin 6 test
5. R78 first-customer E2E review

**MEDIUM:**
6. R76 Cerbos live deploy verify spec
7. R82 Lighthouse nightly artifact review

**LOW (founder approval):**
8. L21 destructive ACTUAL — 6/6 SKIP
9. Mutmut local actual — 5/5 SKIP

---

## 11. LOOP CONTROL

Context dolunca otomatik dur. Founder /resume + Session 11.

---

## 12. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -83
cat artifacts/sprint_q12/master_audit_summary.md
cat _agent-tasks/WORKER_Q12_SESSION_10.md
```

Round 84 = Pricing audit + extract'tan başla. 6 surface × atomic commit. Sonunda hardcoded $ grep boş olmalı.

Engelleyici YOK. Brief eksiksiz. **Bu session, tester teslimat eşiğine yaklaşma close-out session'ı.**
