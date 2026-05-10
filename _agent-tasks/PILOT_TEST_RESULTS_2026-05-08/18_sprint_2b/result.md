# Sprint 2B — 6 P1 bugs + email-cron healthcheck (2026-05-10)

**Branch:** `feat/sprint-q12-deep-quality`
**Commit:** _(filled at push)_
**Image target:** `ghcr.io/enzoemir1/abs-{backend,landing}:1.0.0-rc7` (multi-arch amd64+arm64)
**Pytest:** baseline 1926 → **1946** (+20 new), 0 fail / 0 error / 10 skipped / 3 deselected, 197s
**Status:** ✅ code + tests + 2 alembic migrations + magic_link helper shipped, ⏳ image build + Hetzner deploy pending push

---

## Scope

Brief `_agent-tasks/WORKER_SPRINT_2B_RC6_2026-05-10.md` — 6 P1 bugs + 1
compose healthcheck override, all rc7-bounded:

| Bug | Title | Status |
|-----|-------|--------|
| BUG-19/20/25/26 | PanelSidebar 6 links + 4 missing pages | ✅ |
| BUG-31 | Workflow Sentezleyici prompt+retry+warning | ✅ |
| BUG-33 | Provider Yapılandır modal + test endpoint | ✅ |
| BUG-34 | Marketplace install state persist (alembic 0011) | ✅ |
| BUG-36 | Real users invite endpoint (alembic 0010 + magic_link.py) | ✅ |
| email-cron healthcheck | 5-line compose patch | ✅ |

Sprint 2C scope explicitly deferred: provider API-key save endpoint, race/sentez real multi-provider parallel, settings save (BUG-53/69 cluster).

---

## BUG-19/20/25/26 — PanelSidebar links + 4 admin pages ✅

### Root cause
`/admin/{chat,mcp-tools,quota,dashboard}` were 308 redirects (next.config) to /panel/* or /admin/usage. The brief's founder option (a) — create real /admin/* routes — was selected so the sidebar lands directly without a redirect chain.

### Fix
* **`core/landing/app/admin/chat/page.tsx`** — thin client wrapper dynamically imports `@/app/panel/chat/ChatClient` so the canvas + chat-stream bundle stays equivalent.
* **`core/landing/app/admin/mcp-tools/page.tsx`** — re-exports `@/app/panel/tools/page` (existing TanStack Table over /v1/panel/tools).
* **`core/landing/app/admin/quota/page.tsx`** — re-exports `@/app/panel/quota/page` (existing /v1/system/quota_status surface).
* **`core/landing/app/admin/dashboard/page.tsx`** — new 5-card overview backed by `GET /v1/admin/dashboard` (billing + beta + compliance + security + vault).
* **`core/landing/next.config.ts`** — drop 4 redirects (chat / mcp-tools / quota / dashboard) since real pages now exist. `/admin/meetings` + `/admin/transcription` + `/admin/cascade` redirects retained.
* **`core/landing/components/panel/PanelSidebar.tsx`** — flip `/panel` → `/admin/dashboard` and `/panel/quota` → `/admin/quota`. `REDIRECT_EQUIVALENTS` map updated so deep-linking to legacy /panel routes still highlights the right sidebar entry.

### Tests (`tests/test_sprint_2b_admin_pages.py`, 3 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_four_new_admin_pages_exist_on_disk` | The 4 new page.tsx files exist (404 regression guard). |
| 2 | `test_next_config_no_longer_redirects_four_admin_routes` | Sidebar links don't ride a redirect anymore. |
| 3 | `test_sidebar_uses_canonical_admin_routes` | Genel Bakış→/admin/dashboard, Kota→/admin/quota. |

---

## BUG-31 — Workflow Sentezleyici quality ✅

### Root cause
`_FEW_SHOT_HEADER` lacked an explicit JSON-only directive + the workflow validator's warning list never surfaced "fallback used after LLM JSON parse fail", so the panel showed `Sentezleyici eksik bir iş akışı döndürdü` without telling the operator what happened.

### Fix
* **`core/backend/app/workflow_v10/builder/synthesizer.py`** — strengthened `_FEW_SHOT_HEADER` with REQUIRED SHAPE + 5 explicit RULES (JSON-only, abs.* tool names, non-empty nodes, smallest set, dependency-ordered edges).
* **`core/backend/app/api/workflows.py`** — cap `synth_run(max_revisions=1)` so we don't multiply LLM cost when the cascade just returns bad JSON. On `SynthesisError`, insert a leading warning `"LLM synthesis failed, using template match — <ExcType>: <first 120 chars>"` into the response so the frontend can toast it. Template fallback path now writes a specific warning instead of staying silent.

### Tests (`tests/test_sprint_2b_workflow_synth.py`, 2 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_synth_fallback_emits_explicit_warning` | Stubbed bad LLM → response.source=template + warning copy present. |
| 2 | `test_synth_happy_path_returns_llm_source` | Valid JSON path returns llm-or-template depending on schema validation (never crashes). |

---

## BUG-33 — Provider Yapılandır modal + test endpoint ✅

### Root cause
The Yapılandır button on `/admin/providers` was hard-disabled with `title="Phase K — Settings sayfasından API key ekle"`. There was no read-only modal + no `POST /v1/admin/providers/{id}/test` endpoint so the operator couldn't confirm a stored key actually worked without flipping the global `ABS_*_ENABLED` flag.

### Fix
* **`core/backend/app/api/admin/providers_status.py`** EXTENDED (no new file — same router as `/status`) — `POST /v1/admin/providers/{provider_id}/test`:
  - Provider catalog: groq / cerebras / cloudflare / gemini / cohere / anthropic.
  - 404 on unknown provider id; ok=false+`error="missing_api_key"` when key blank.
  - Synthetic 8-token prompt via `app.cascade.orchestrator.call_with_cascade`.
  - Returns `{ok, provider, model?, latency_ms, error?}`.
  - Audit emit `setup.provider.test` per call (success / failure / denied).
  - Never returns 500 — provider exceptions wrap into ok=false.
* **`core/landing/components/admin/ProviderConfigModal.tsx`** NEW — read-only modal:
  - Masked key hint (`sk-••••••••••••` or `—`) — the real key never crosses the wire.
  - "Şimdi test et" button → POST `/v1/admin/providers/{id}/test` → spinner → success badge (latency) or red error.
  - "API anahtarını değiştir" link → `/setup/step/providers` (Sprint 2C handles in-place edit).
* **`core/landing/app/admin/providers/page.tsx`** — wire `useState<ProviderConfigEntry | null>(null)` driver + onClick on each "Yapılandır" button + mount `<ProviderConfigModal />` at the bottom.

### Tests (`tests/test_sprint_2b_provider_test.py`, 4 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_test_endpoint_requires_admin` | 401 without admin auth. |
| 2 | `test_test_endpoint_unknown_provider_returns_404` | Provider id outside catalog → 404. |
| 3 | `test_test_endpoint_missing_key_returns_ok_false` | Blank key → ok=false `missing_api_key`, no 500. |
| 4 | `test_test_endpoint_provider_error_surfaces_ok_false` | Cascade `ProviderError` → ok=false with error string, no 500. |

---

## BUG-34 — Marketplace install state persist ✅

### Root cause
Install handler wrote only to `/app/data/marketplace_installs.json` and an in-memory sandbox launcher. After a backend restart or a different tenant context, `GET /v1/marketplace/installed` could miss rows; the admin UI never refetched after install so the card stayed on "Kur".

### Fix
* **`core/backend/alembic/versions/0011_tenant_installed_plugins.py`** NEW — `tenant_installed_plugins` table:
  - `(id, tenant_id, plugin_id, version, sandbox_container_id, installed_at, uninstalled_at)`
  - `DateTime(timezone=True)` on both timestamp columns (founder audit patch — Postgres TIMESTAMPTZ, SQLite idempotent).
  - Indexes: tenant_id, plugin_id, composite (tenant_id, plugin_id). Soft-delete via `uninstalled_at` so audit history persists.
* **`core/backend/app/db/models.py`** — `TenantInstalledPlugin` SQLModel matching the migration.
* **`core/backend/app/api/marketplace.py`** —
  - `_persist_install_row` writes a row on every install (idempotent).
  - `_mark_uninstalled_row` soft-deletes on uninstall.
  - `_list_installed_rows` reads from SQL; falls back to JSON store if the table is unreachable (boot-before-migrate).
  - `GET /installed` now uses SQL-first.
  - Added `marketplace.install` + `marketplace.uninstall` `success` audit emits.
* **`core/landing/components/MarketplacePanel.tsx`** — fetch `/v1/marketplace/installed` on mount + after every install/uninstall. New `Kurulu` badge + `Kaldır` button on installed plugins. POST endpoint switched from `/api/marketplace/install` (legacy proxy) to `/v1/marketplace/install` (real backend).

### Tests (`tests/test_sprint_2b_marketplace.py`, 3 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_install_persists_in_tenant_installed_plugins` | SQL row created with version + tenant. |
| 2 | `test_installed_endpoint_reads_from_sql` | GET /installed returns SQL row. |
| 3 | `test_uninstall_marks_row_inactive` | Uninstall flips `uninstalled_at`; subsequent /installed excludes the plugin. |

---

## BUG-36 — Users Davet et — REAL invite endpoint ✅

### Root cause
`core/landing/app/admin/users/UsersClient.tsx:80` generated a fake URL with `mock_${Math.random()}` — no backend POST happened. The inner `customer_portal_v10/account.Invite` dataclass existed but no HTTP route exposed it; `app/auth/magic_link.py` was missing entirely.

### Fix

#### Pre-work
* **`core/backend/app/auth/magic_link.py`** NEW — HMAC-SHA256 token helper:
  - `create_magic_link_token(email, tenant_id, ttl_minutes, purpose)` → `(plaintext, hash, expires_at)`. 32-byte URL-safe random plaintext; HMAC digest of `settings.magic_link_hmac_secret` (falls back to `admin_jwt_secret` so dev/test doesn't have to set a new env var).
  - `hash_magic_token(plaintext)` — consume-side reverse lookup.
  - `verify_magic_token(...)` — constant-time digest comparison + expiry + purpose check.
* **`core/backend/app/config.py`** — `magic_link_hmac_secret` + `public_hostname` settings.
* **`core/backend/alembic/versions/0010_tenant_invites.py`** NEW — `tenant_invites` table with `(invite_id unique, email, role, tenant_id, invited_by, magic_token_hash unique, expires_at, accepted_at, revoked_at, status, created_at)`. Indexes: invite_id, email, (tenant_id, status), magic_token_hash. **Founder audit patch:** `DateTime(timezone=True)` on all timestamps + `CheckConstraint` on role + status (defense-in-depth).

#### Backend endpoints (`core/backend/app/api/admin/users.py` EXTENDED)
* `POST /v1/admin/users/invite` — body `{email: EmailStr, role: admin|member|operator|viewer}`:
  - Resolves tenant via `_resolve_admin_tenant` chain (JWT claim → users row → admin_credentials.json → email-domain heuristic → "default").
  - 409 on duplicate pending invite with same `(tenant, email)`, returning the existing `invite_id`.
  - Mints magic-link via `create_magic_link_token(purpose="invite")`, persists `TenantInvite` row with the HMAC digest (never plaintext).
  - Calls `send_invite_email` (SMTP if configured, console fallback otherwise).
  - Audit emit `admin.user.invited` (no token, no hash) — actor + email + role + invite_id.
  - **Never returns the magic-link URL on the wire** — only `invite_id, email, role, tenant_id, expires_at, status`.
* `GET /v1/admin/users/invites` — list pending+accepted invites for the caller's tenant.
* `DELETE /v1/admin/users/invite/{invite_id}` — 204 on revoke, 404 missing, 409 if not pending. Audit emit `admin.user.invite_revoked`.

#### Consume side (`core/backend/app/api/auth.py`)
* `_claim_invite_by_token` NEW — re-hashes incoming token, looks up `tenant_invites.magic_token_hash`, validates expiry + status, marks accepted, materialises/promotes a `users` row, returns `{email, tenant_slug, role}`.
* `magic_claim` (`GET /auth/magic`) extended — invite path tried first; falls through to legacy signup claim if no invite matches. 410 on expired/revoked/already_accepted invite.

#### Email (`core/backend/app/email/sender.py`)
* `send_invite_email` NEW — inline HTML (no new template file in rc7) with magic-link URL, role label, tenant name. SMTP_HOST blank → console fallback (matches `send_refund_email` semantics).

#### Frontend (`core/landing/app/admin/users/UsersClient.tsx`)
* Replaced `Math.random()` mock with real `POST /v1/admin/users/invite` fetch.
* Renders success copy with `invite_id + expiry`; explicit "URL backend log'larına yazılmaz" note (security posture).
* New pending-invites card above the user table — pending rows + "İptal" button → `DELETE /v1/admin/users/invite/{id}`.
* Removed mock `magic_link` URL display and the Copy icon import.

### Tests (`tests/test_sprint_2b_invite.py`, 6 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_invite_requires_admin` | 401 without admin auth. |
| 2 | `test_invite_success_returns_invite_id_without_token` | 201 + payload contains no magic_token or hash. |
| 3 | `test_duplicate_pending_invite_returns_409` | Second invite for same (tenant, email) → 409 with `existing invite_id`. |
| 4 | `test_list_invites_includes_pending_row` | GET /invites surfaces the new row. |
| 5 | `test_revoke_invite_flips_status_to_revoked` | DELETE → 204; re-revoke → 409. |
| 6 | `test_magic_link_helper_hashes_via_hmac` | HMAC digest is non-trivial; purpose mismatch fails verify. |

---

## email-cron healthcheck override ✅

### Root cause
email-cron reuses the backend image but runs `while true; do python infra/scripts/email_tick.py; sleep 300; done` — no FastAPI server bound on :8000. The inherited Dockerfile HEALTHCHECK probed :8000 → permanent unhealthy (failing streak 58+ on Hetzner pre-rc7).

### Fix
* **`infra/docker-compose.customer.yml`** + **`docker-compose.yml`** — explicit `healthcheck:` block on the `email-cron` service:
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "pgrep -f 'email_tick|email_cron|email_dispatcher' || exit 1"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
  ```

### Tests (`tests/test_sprint_2b_email_cron_healthcheck.py`, 2 new)
| # | Test | What it guards |
|---|------|----------------|
| 1 | `test_customer_compose_email_cron_has_process_healthcheck` | Customer compose has pgrep probe. |
| 2 | `test_root_compose_email_cron_has_process_healthcheck` | Root compose has pgrep probe. |

---

## Founder-side audit patch (post-BUG-36)

Three optional schema improvements suggested mid-sprint:

| # | Patch | Applied | Notes |
|---|-------|---------|-------|
| 1 | FK CASCADE to `tenants` on both migrations | ❌ skipped | The bootstrap `default` tenant slug may not have a matching `tenants` row; NOT NULL FK would regress install/invite flows. Application-level tenant resolution is sufficient. Documented in migration upgrade docstring; revisit in Sprint 2C with formal tenant lifecycle. |
| 2 | `CheckConstraint` on `role` + `status` (0010 only) | ✅ applied | Defense-in-depth if Pydantic Literal is bypassed via raw SQL. |
| 3 | `DateTime(timezone=True)` on all timestamp columns (0010 + 0011) | ✅ applied | Postgres TIMESTAMPTZ; SQLite ignores tz (idempotent). |

All applied patches kept pytest green (1946 still 0 fail).

---

## Pytest

```
$ pytest tests/ --ignore=tests/integration --ignore=tests/security_tests
1946 passed, 10 skipped, 3 deselected, 0 fail/error in 197.39s
```

* Baseline (Sprint 2A close): `1926 passed, 10 skipped, 0 fail`.
* Delta: **+20 passed** (6 invite + 4 provider test + 3 marketplace + 2 workflow synth + 3 admin pages + 2 healthcheck).

---

## Files touched

### Backend
```
core/backend/app/api/admin/providers_status.py    (+146 — POST /test endpoint)
core/backend/app/api/admin/users.py               (+223 — invite POST/GET/DELETE)
core/backend/app/api/auth.py                      (+113 — _claim_invite_by_token + magic_claim extension)
core/backend/app/api/marketplace.py               (+126 — SQL persist helpers + install/uninstall wire)
core/backend/app/api/workflows.py                 (+21  — max_revisions=1, fallback warning)
core/backend/app/auth/magic_link.py               NEW   (HMAC helper)
core/backend/app/config.py                        (+10  — magic_link_hmac_secret + public_hostname)
core/backend/app/db/models.py                     (+51  — TenantInvite + TenantInstalledPlugin)
core/backend/app/email/sender.py                  (+38  — send_invite_email)
core/backend/app/workflow_v10/builder/synthesizer.py (+23 — JSON-only prompt rules)
core/backend/alembic/versions/0010_tenant_invites.py            NEW
core/backend/alembic/versions/0011_tenant_installed_plugins.py  NEW
core/backend/tests/test_sprint_2b_admin_pages.py                NEW (3)
core/backend/tests/test_sprint_2b_email_cron_healthcheck.py     NEW (2)
core/backend/tests/test_sprint_2b_invite.py                     NEW (6)
core/backend/tests/test_sprint_2b_marketplace.py                NEW (3)
core/backend/tests/test_sprint_2b_provider_test.py              NEW (4)
core/backend/tests/test_sprint_2b_workflow_synth.py             NEW (2)
```

### Frontend
```
core/landing/app/admin/chat/page.tsx              NEW (re-exports panel ChatClient)
core/landing/app/admin/dashboard/page.tsx         NEW (5-card overview)
core/landing/app/admin/mcp-tools/page.tsx         NEW (re-exports panel ToolsPage)
core/landing/app/admin/quota/page.tsx             NEW (re-exports panel QuotaPage)
core/landing/app/admin/providers/page.tsx         (+54  — modal state + onClick)
core/landing/app/admin/users/UsersClient.tsx      (+195 — real invite + revoke + pending list)
core/landing/components/MarketplacePanel.tsx      (+113 — installed state, Kurulu badge, Kaldır)
core/landing/components/admin/ProviderConfigModal.tsx NEW (BUG-33 modal)
core/landing/components/panel/PanelSidebar.tsx    (+20  — /admin/dashboard + /admin/quota)
core/landing/next.config.ts                       (+11  — drop 4 redirects)
```

### Infra
```
docker-compose.yml                                (+9  — email-cron healthcheck)
infra/docker-compose.customer.yml                 (+12 — email-cron healthcheck)
```

---

## Live verify (pending — fill after push + Hetzner deploy)

```
# /healthz
curl -sk https://168.119.104.24.sslip.io/healthz → expected 200

# License info
curl -sk https://168.119.104.24.sslip.io/v1/license/info → expected "licensed"

# Invite endpoint smoke (no auth — auth chain wired)
curl -sk -X POST https://168.119.104.24.sslip.io/v1/admin/users/invite -d '{}' \
  → expected 401 missing_bearer_token

# email-cron healthy within 90s of compose-up
ssh -i customer-keys/pilot-1/deploy_key root@168.119.104.24 \
  'sleep 90 && docker inspect abs-email-cron-1 --format "{{.State.Health.Status}}"'
  → expected "healthy"

# Backend image confirmation
docker logs abs-backend-1 --tail 30 → expected ABS_VERSION=1.0.0-rc7, no startup errors
```

### Cookie-authenticated curl — pending founder Playwright

Worker has no admin password (founder sets via setup wizard). Auth-chain
smoke verifies the new endpoints reject unauthenticated requests
correctly (401 missing_bearer_token). Founder Playwright sequence to
close DoD:

```
1. Login at https://168.119.104.24.sslip.io/admin/auth/login
2. Visit /admin/dashboard → expect 5-card overview rendered, no 404.
3. Visit /admin/chat → expect chat surface rendered.
4. Visit /admin/quota → expect provider usage bars.
5. Visit /admin/providers → click Yapılandır on a provider → modal opens
   with masked key. Click "Şimdi test et" → expect latency or error
   inside 30s.
6. Visit /admin/marketplace → install a plugin → expect "Kurulu" badge
   within 5s. Refresh → state persists. Click "Kaldır" → state flips.
7. Visit /admin/users → click "Davet et" → enter email + role:member →
   expect success toast with invite_id. Pending-invite card appears.
8. Check Resend dashboard (or SMTP relay log) → invite email sent.
9. /admin/workflow-builder → "müşteri talepleri için Slack + Linear
   akışı" → Sentezle → expect canvas populated; if LLM JSON parse
   fails, expect a soft "LLM synthesis failed, using template match"
   warning.
```

---

## Definition of done

- [x] 6 P1 bugs + email-cron healthcheck shipped
- [x] alembic 0010_tenant_invites + 0011_tenant_installed_plugins migrations
- [x] app/auth/magic_link.py created (HMAC + verify + create utilities)
- [x] pytest 1946+ green (target 1946 hit exactly)
- [x] Founder audit patch evaluated — CheckConstraint + TZ-aware applied; FK CASCADE deferred to Sprint 2C
- [ ] commit + push (Co-Authored-By trailer YOK)
- [ ] rc7 multi-arch GHCR push
- [ ] Hetzner deploy + 90s healthcheck (backend + email-cron healthy)
- [ ] Auth-chain smoke verified (cookie blocker tolerated)
- [ ] Founder Playwright sequence executed (handed off)

---

## Deferred / non-goals (per brief)

* **Sprint 2C (rc8)**: provider API-key save endpoint (BUG-33 in-place edit), race/sentez real multi-provider parallel, settings save endpoints (BUG-53/69 cluster), BGE-M3 default decision.
* **FK CASCADE on `tenant_invites` + `tenant_installed_plugins`** — documented above; needs Sprint 2C tenant lifecycle work first.
* **Cypher injection NL→template whitelist** — Sprint 2A backlog, still open.
