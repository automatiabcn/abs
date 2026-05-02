# Q12 — Round 13 — L23 observability gap

**Tarih:** 2026-05-03
**Layer:** L23 — observability gap (Q12 Session 2 yeni)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Brief'in L23 talebi: her error path traceable mi? Structured log
(request_id, tenant_id, user_id, action, outcome). Metric counter
consistency. OpenTelemetry trace span her endpoint.

Beklenen: 5–20 endpoint'te eksik logging path.

---

## 1. Quantitative gap audit (pre-fix baseline)

`core/backend/app/api/` altındaki 32 router dosyasında raise + log
pairing tarandı. Bir raise sitesini "logged" sayma kuralı: 4 satır
öncesinde `logger.{warning|error|exception|info|critical}` çağrısı.

```
files_total: 32
raise_total: 147
raises_with_log_within_3: 9   ← 6.1%
raises_silent: 138            ← 93.9%
```

**Top silent offenders (file → silent/total):**
- `me_account.py` 11/11
- `me_data_export.py` 10/10
- `setup.py` 8/8
- `admin/auth.py` 8/9
- `auth.py` 7/7
- `smart_link.py` 7/7
- `beta_admin.py` 7/7
- `meetings.py` 6/6
- `me_consent.py` 6/6
- `mcp_tokens.py` 6/6
- `chat.py` 5/5
- `marketplace.py` 5/5

**Yan bulgu — yapısal eksik:**
- `grep -rn "import structlog" core/backend/app/` → 0 hit. Tüm modüller
  default Python logging (text formatter) kullanıyor.
- `core/backend/app/main.py` middleware stack'i: `FirstRunMiddleware`,
  `I18nMiddleware`, `DemoModeMiddleware`. **Hiçbir RequestIDMiddleware
  yok**. Yani aynı incident'ı nginx → backend → cerbos → DB hattında
  korelasyon kurmak için `request_id` header taşınmıyor.
- `request.state.lang` set ediliyor ama `request.state.request_id`
  set edilmiyor.

---

## 2. Q12-L23-001 — HIGH (observability blocker)

**Bulgu:** 138/147 (93.9%) raise sitesi sessizce 4xx/5xx döndürüyor;
log/metric/trace yok. Üstüne korelasyon ID middleware'i de yok.

**Ops impact:**
- Credential stuffing /auth/login → görünmez (raise 401 silent).
- Expired token replay → görünmez.
- Cross-tenant Cerbos DENY → cerbos middleware log üretiyor ama request
  korelasyonu için ID yok; bir incident'ı ileri taşıma maliyeti yüksek.

---

## 3. Shipped — Option A fix (request_id middleware + emit_event)

GPT-OSS 120B analizi (delegation MCP) Option A'yı önerdi: **küçük
blast radius, geri kalan tüm raise sitelerine fundament**.

### `core/backend/app/middleware/request_id.py` (37 LoC)

`BaseHTTPMiddleware` (mevcut i18n/demo_mode pattern'iyle uyumlu).

- `X-Request-ID` header'ı oku → safe (alphanum + `-_`, ≤128 char) ise
  preserve, değilse uuid4 hex generate.
- `request.state.request_id` set.
- Response header'ında geri yansıt.
- `main.py`'de **outermost** mount (LIFO sıralama: en son
  `add_middleware` ilk çalışır).

### `core/backend/app/observability/audit.py` (88 LoC)

`emit_event(request, *, action, outcome, **ctx)` tek giriş noktası.

- Logger: `abs.audit` (ayrı handler'a route edilebilir).
- Outcome enum: `{success, failure, denied, error}` — invalid değer
  `error`'a normalize.
- PII guard-rail: `SAFE_KEYS` allowlist'i (reason, tenant_id, user_id,
  email_hint, provider, status_code, vs.) **dışındaki** her key drop
  edilir. Plus `password*`, `secret*`, `api_key*`, `token*`,
  `cookie*`, `authorization*`, `bearer*`, `private*` prefix'leri
  açık şekilde drop.
- Record `extra={"audit": payload}` ile yazılır → caplog
  `getattr(rec, "audit", {})` ile yapısal okuma.

### `auth.py` patch

İlk hot-spot. **5 yeni emit_event** çağrısı:
- `current_admin` missing-cookie → `auth.session.check denied missing_cookie`
- `current_admin` decode failure → `auth.session.decode denied (expired|invalid)`
- `login` bad email → `auth.login denied email_no_source` (email_hint masked)
- `login` password mismatch → `auth.login denied password_mismatch` (count of candidates)
- `login` success → `auth.login success` (provider, masked email_hint)
- `magic_claim` 3 paths → `auth.magic.claim denied (invalid_token|token_not_found|token_expired)`
- `me` missing-cookie → `auth.me.check denied missing_cookie`

Email asla full-form yazılmıyor: `email[:3] + "***"` (örn. `eda***`).

---

## 4. Shipped — `core/backend/tests/test_q12_l23_observability.py` (9 test)

```
TestQ12L23RequestIDMiddleware:
  test_request_id_generated_when_absent     ← uuid4 hex (32 chars)
  test_request_id_preserved_when_safe        ← alphanum echoed verbatim
  test_request_id_replaced_when_malformed    ← banned char → replace
  test_request_id_replaced_when_too_long     ← >128 char → replace

TestQ12L23EmitEventScrub:
  test_unknown_keys_dropped                  ← arbitrary + secret keys → drop
  test_safe_keys_set_is_explicit             ← regression guard for allowlist
  test_outcome_normalized_to_error_when_invalid

TestQ12L23LoginAuditTrail:
  test_login_email_no_source_emits_denied    ← masked email_hint, request_id present
  test_login_no_secret_field_in_audit_record ← no password/api_key/secret/token/cookie key
```

**Sonuç: 9 passed in 1.81s**

Full backend regression: `1484 passed, 1 cwd-only failure` (Q11-L14
alembic.ini relative path issue — pytest cwd = repo root yerine
`core/backend/`; isolated re-run from correct cwd: 1 PASS). Net Q12
Session 1 1473 → Session 2 1485 (+12: 9 L23 tests + diğer).

---

## 5. Layer state

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| **L21** | **1/3** | fresh-deploy drill (safe variant 3/3 PASS) |
| **L22** | **0/3** | pending Round 15 |
| **L23** | **1/3** | observability fix (req_id + emit_event + auth.py + 9 tests) |
| **L24** | **0/3** | pending Round 14 |
| **L25** | **0/3** | pending Round 17 |
| **L26** | **0/3** | pending Round 16 |

---

## 6. Q12-L24 ön-bulgu (Round 14 input)

L23 audit sırasında auth.py'da L24 candidate yakalandı:

```python
# core/backend/app/api/auth.py:428
logger.info(
    "signup_pending email=%s slug=%s magic=/auth/magic?token=%s",
    body.email, body.tenant_slug, token,
)
```

**Magic token plaintext olarak audit log'a yazılıyor**. 24h boyunca
geçerli ve tek atımda admin oturumu açıyor. Log file'a read access
olan herhangi biri (ops, log aggregator vendor, accidental disclosure)
hesabı claim edebilir. Round 14'te ilk fix.

---

## 7. Atomic commit

```
fix(q12/L23): Round 13 RequestIDMiddleware + emit_event helper + auth.py audit trail — 9/9 tests PASS, 1485 full suite green
```
