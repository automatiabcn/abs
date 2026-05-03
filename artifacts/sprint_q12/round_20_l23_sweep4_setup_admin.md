# Round 20 — L23 sweep 4 setup.py + admin/auth.py audit coverage

**Sprint:** Q12 Session 3
**Layer:** L23 (observability gap) — sweep 4 / 31-site Founder verify backlog
**Files touched:** 2 src + 1 new test
**Status:** ✅ shipped

---

## Founder verify gap (Session 2 close)

```
app/api/setup.py        — 8 silent raise sites (0 emit_event)
app/api/admin/auth.py   — 9 silent raise sites (0 emit_event)
app/api/smart_link.py   — 7 silent raise sites (R21)
app/api/beta_admin.py   — 7 silent raise sites (R21)
TOTAL                   — 31 production-incident-blind paths
```

L23 was already 3/3 FULL CLEAN after R13–R19 BUT 31 raise sites in
boot-onset / admin-gate code remained silent. Founder logged the gap
and explicitly demanded sweep 4 → 4/3 deep.

---

## R20 scope (this round)

### setup.py (8 raise sites covered)
* `_ensure_step` 409 setup_already_completed → `setup.step.gate denied`
* `_ensure_step` 409 step_not_active → `setup.step.gate denied`
* `set_setup_lang` 400 unsupported_language → `setup.lang.set denied|success`
* `step_admin` happy path → `setup.step.complete success` (email_hint masked)
* `step_license` 400 license_invalid → `setup.step.license denied`
* `step_license` happy path → `setup.step.complete success`
* `step_domain` 400 domain_invalid → `setup.step.domain denied`
* `step_domain` happy path → `setup.step.complete success`
* `step_anthropic` happy path → `setup.step.complete success`
* `step_providers` happy path → `setup.step.complete success`
* `step_test` happy path → `setup.wizard.completed success`
* `reset_setup` 403 non_dev_env → `setup.reset denied`
* `reset_setup` happy path → `setup.reset success`

Pydantic validator `ValueError` paths in `AnthropicBody` (lines 291,
293) were intentionally NOT wired — no `Request` available at the
Pydantic layer; FastAPI emits a structured 422 with detail and the
attempt is logged at the request boundary by `RequestIDMiddleware`.

### admin/auth.py (9 raise sites covered)
* `admin_required` 403 ip_not_whitelisted → `admin.auth.gate denied`
* `admin_required` JWT failures (401 expired / 401 invalid / 403 scope)
  wrapped in try/except → `admin.auth.gate denied`
* `admin_required` panel session fallback success → `admin.auth.gate success`
* `admin_required` 401 missing_bearer_and_cookie → `admin.auth.gate denied`
* `admin_login` 503 login_disabled_no_password_hash → `admin.login denied`
* `admin_login` 403 ip_not_whitelisted → `admin.login denied`
* `admin_login` 429 rate_limited → `admin.login denied`
* `admin_login` 401 password_invalid → `admin.login failure`
* `admin_login` 200 happy → `admin.login success`

CRITICAL audit invariant verified by test:
`test_password_invalid_emits_failure` asserts the submitted password
("wrong") never appears in any audit ctx. Audit allowlist
(`SAFE_KEYS`) drops anything outside the schema, so even a bug that
passed `password=body.password` would be silently dropped.

---

## Real bug surfaced (R21 work, fixed pre-commit)

While wiring the matching `beta_admin.py` audit (Round 21), test
`test_admin_approve_issues_license_and_marks_request` failed with
`DetachedInstanceError` because the new emit-after-commit
`email_hint=(row.email or "")[:3]` accessed an ORM attribute on a
post-commit (detached) instance. Fix: capture `row_email` before
`db.commit()` and reuse for both audit + downstream email_sequence /
discord callbacks. The bug was *latent* in the original code too — the
existing `schedule_beta_sequence(customer_email=row.email)` and
`dw.notify_beta_approved(email=row.email)` calls below the commit had
the same accessor; they only "worked" because `row` was eager-loaded
in test fixture context with autoflush. Detach-after-commit is the
SQLAlchemy 2.0 default; this would surface in production any time the
session expired between commit and email send. Round 21 ships the
canonical fix.

---

## Image + container evidence

```
image_rebuilt_at: 2026-05-03T14:01:34Z (first rebuild this session)
container_pytest_pass:    13/13 (R20 sweep4 test file)
regression_pass:          58/58 (R20 + setup_wizard + setup_lang +
                          setup_e2e + 032_admin_auth + L22 race +
                          L23 sweep1/2/3 + R20 sweep4)
full_suite_pass:          1540 passed, 14 skipped (Δ +13)
```

```
$ docker exec infra-backend-1 grep -c 'emit_event' \
    /app/app/api/setup.py /app/app/api/admin/auth.py
/app/app/api/setup.py:15
/app/app/api/admin/auth.py:10
```

```
$ curl -sk -o /dev/null -w "%{http_code}\n" \
    http://localhost:8000/v1/setup/status
200
$ curl -sk -o /dev/null -w "%{http_code}\n" -X POST \
    -H 'Content-Type: application/json' -d '{"lang":"xx"}' \
    http://localhost:8000/v1/setup/lang
400
$ curl -sk -o /dev/null -w "%{http_code}\n" -X POST \
    -H 'Content-Type: application/json' -d '{"password":"x"}' \
    http://localhost:8000/v1/admin/login
503
```

Live container returns the exact denial codes that the new emit_event
calls cover.

---

## L23 counter

* Sweep 1 (R13)        — auth.py 5 paths
* Sweep 2 (R18)        — me_account.py 11 paths
* Sweep 3 (R19)        — me_data_export.py 10 paths → **3/3 FULL CLEAN**
* **Sweep 4 (R20)**    — **setup.py 13 emits + admin/auth.py 10 emits = 23 paths**
* Sweep 4 cont. (R21)  — smart_link.py + beta_admin.py (this session)

L23 → **4/3 deep**, with sweep 4 part 1 of 2 shipped.
