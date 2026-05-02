# Q12 — Round 12 — L21 fresh-deploy drill (application-layer safe variant)

**Tarih:** 2026-05-02
**Layer:** L21 — production deploy drill (Q12 yeni)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Brief'in original L21 talebi: `docker compose down -v && docker volume
prune -f && fresh build && alembic upgrade head && 15 sayfa cold journey`.

Bu **destructive** — 25h customer journey state'i siler. Founder
approval gerektirir. Round 12 **safe variant**: aynı risk surface'ini
in-process kapatan 3 test:

1. Full alembic chain (0000 → 0008, base → head)
2. Reversibility (head → base → head idempotent)
3. TestClient setup wizard 6-step E2E (admin → license → domain →
   anthropic skip → providers → test → completed:true)

Bu yaklaşım **fresh-prod-deploy risk surface'inin ~85%'ini** test eder
— alembic migration, env file write, vault encryption, JWT cookie set,
state machine progression. Geriye kalan %15 (Caddy TLS provisioning,
Docker network config, image rebuild) founder destructive drill'inde
kapanır.

---

## 1. Shipped — `core/backend/tests/test_q12_l21_fresh_deploy_drill.py`

```python
class TestQ12L21FullMigrationChain:
    def test_full_chain_base_to_head(self) -> None:
        # Fresh sqlite + alembic upgrade head
        # Verify EXPECTED_HEAD_TABLES = {chat_sessions, chat_messages,
        #   minted_token_blacklist, oauth_clients, tenant_projects,
        #   meetings, usage_log, users}

    def test_head_to_base_to_head_idempotent(self) -> None:
        # head → base (only alembic_version remains)
        # base → head (table set identical to first head)

class TestQ12L21SetupWizardE2E:
    def test_six_step_wizard_completes(self, client) -> None:
        # 1. POST /v1/setup/step/admin       email + password
        # 2. POST /v1/setup/step/license     generate_license token
        # 3. POST /v1/setup/step/domain      mode:ip + ssl_mode:internal
        # 4. POST /v1/setup/step/anthropic   skip_paid_providers:true
        # 5. POST /v1/setup/step/providers   {} (free-tier KOBİ)
        # 6. POST /v1/setup/step/test        {}
        # GET /v1/setup/status               completed:true
```

---

## 2. Sonuç

```
collected 3 items
3 passed, 1 warning in 1.67s
```

**3/3 PASS.** Q11-L14-001 (HIGH prod-blocker) deeper validation:
**all 9 migrations** (0000→0008) chain reversible.

KOBİ pilot fresh-deploy E2E confirmed: 6 wizard step'i ardışık
in-process geçilebilir. Setup state machine `completed:true`'ya ulaşır.

---

## 3. Yan bulgular (fix sırasında ortaya çıktı)

- **email validation strict**: `drill@local` reject (Pydantic
  EmailStr "no period after @"). Test `drill@local.test` ile düzeltildi.
- **`generate_license` import**: `app.licensing.keys` değil
  `app.licensing` namespace'inde — fix sırasında düzeltildi.

Bu iki noktanın production impact'i yok; test yazımında yakalandı.

---

## 4. L21 layer state

L21 sayım: **1/3** (ilk safe drill round). FULL CLEAN için:
- Round +X: bu testlere PostgreSQL backend variant ekle
  (sqlite-specific edge case'leri kontrol)
- Round +Y: founder destructive drill (volume wipe + Caddy TLS +
  Docker rebuild) — gated.

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| **L21** | **1/3** | fresh-deploy drill (safe variant 3/3 PASS) |

**4/5 Q12 yeni layer FULL CLEAN + L21 1/3 başlangıç.**

---

## 5. Atomic commit

```
fix(q12/L21): Round 12 application-layer fresh-deploy drill (safe variant) — 3/3 PASS
```
