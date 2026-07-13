# Changelog

Version history — one line per change, date + delta.

## 1.0.6 (2026-05-25) — Audit hardening (11 fixes)

Full-system audit across five lenses (rendering/function, design intent,
security, resilience, E2E). Fixes:
- **Cascade now defaults to the free path** — `PROVIDER_ORDER_DEFAULT`
  (Groq → … → Anthropic as the last fallback), aligned with
  `ABS_HYBRID_TIER_PROMISE`; chat + cascade + workflows all default to the free
  path. The UI `providers_status` follows the same order.
- **Graph NL→Cypher** called `cascade_call` (which does not exist) → now uses
  `call_with_cascade` + JSON-fence strip.
- **Single source of truth for the version** — `settings.version` (ABS_VERSION)
  → status/main/footer/pyproject.
- **`configs.py` `_default_dir()`** guards the `parents[4]` IndexError
  (a cold deploy without env crashed).
- **Empty graph/cypher** 500 → 422, **empty graph/nl-query intent** 502 → 422.
- **Panel cascade** now returns `providers_active` + `timeseries` (the panel
  showed "0").
- **admin/usage** merges the live `usage_log` from the DB + `cerebras` added to
  FREE_PROVIDERS.
- **RAG** `GET /v1/rag/documents` + `qc.list_documents` (the page now shows the
  store).
- Quota header overlap (flex-wrap), /admin/audit React #418 (timeZone pin).

Security sweep clean: auth-required endpoints return 401, tenant isolation
holds, rate limit returns 429, destructive cypher 400, forged MCP token 401, no
secret leaks. Known open ends: the admin panel is not internationalized
(Turkish only), and the GitHub Smart Link OAuth flow is a placeholder.

## 1.0.4 (2026-05-16) — Docs alias split (v1.0.3 yellow → green)

Single change: `docs.yml` now derives `MIKE_VERSION` from `github.ref_name`
(tag → `v1.0.x`, push to main → `main`); the `latest` alias is updated on a
separate channel. This closes the version+alias collision that was the root
cause of the previous 5 consecutive failures (run 25968243819 and earlier). The
docs workflow is GREEN for the first time; `docs.automatiabcn.com/v1.0.4/` and
`/` (alias) are live. Merge commit `f433dcb`, run 25968714499.

All v1.0.3 changes carry over; the runtime image content is unchanged (backend
+ landing were re-pushed with the `:1.0.4` + `:latest` tags). The only change
for a customer upgrade is `ABS_VERSION=1.0.4` in `.env`.

See the v1.0.3 entry for the previous release.

## 1.0.3 (2026-05-16) — Hot-patch (release GA, docs gap open)

In the v1.0.1 and v1.0.2 releases the release.yml workflow reported green even
though no customer image existed on ghcr.io — upgrades and new deployments were
blocked with HTTP 404. Two hot-patch rounds closed 4 + 4 gaps; v1.0.3 is the
first release that actually ships an image.

**The one gap still open:** the docs / mike deploy still fails with
`duplicated version and alias` (run 25968243819). It will be closed by a
single-fix patch chain (`docs.yml` resolve-version step + alias/version split).
Because of this, docs.automatiabcn.com does not reflect the v1.0.3 pages; the
GitHub Release notes + this CHANGELOG are canonical.

### Fixes — hot-patch round 1 (3)

- **Postgres CI** — oauth_clients migration `BOOLEAN DEFAULT 0` →
  `DEFAULT FALSE`; alembic revision id 36 chars → 24 chars (the varchar(32)
  `alembic_version` limit); env.py gained a legacy revision rewrite shim, so
  SQLite customers stay backward compatible.
- **release.yml** — added the `publish-images` job (cosign-sign was signing when
  no image existed); matrix backend+landing build+push + provenance + SBOM +
  cosign keyless chain.
- **docs mike deploy** — idempotent first attempt (improved in round 2, closed
  in v1.0.4 — the `grep` regex did not match the `[latest]` brackets).

### Fixes — hot-patch round 2 (3 closed + 1 partial)

- **Backend Dockerfile** pubkey path → `app/update/manifest_pubkey.pem` (the
  sibling `core/backend/manifest_pubkey.pem` was gitignored by `*.pem`, so the
  CI checkout was missing it). Release backend GREEN.
- **GHCR namespace** `enzoemir1` → `automatiabcn` (the workflow GITHUB_TOKEN
  cannot push cross-account; `permission_denied: installation does not exist`).
  The customer compose is parametrized via the `ABS_GHCR_NAMESPACE` env var,
  default `automatiabcn`. Release landing GREEN.
- **docs mike pre-delete** made unconditional. Partial: `mike delete latest`
  removes the alias but leaves the version behind, so the next deploy hits the
  same duplicate error. Carried to v1.0.4.
- **CI Postgres RLS** 5 failing tests — two role models (`abs_app` SUPERUSER for
  alembic, `abs_app_rls` NOSUPERUSER NOBYPASSRLS for data ops), GUC leak fixed
  with NullPool, downgrade test restores LOGIN + grants in `finally`. CI
  Postgres 7/7 GREEN.

### Infra ship (v1.0.3)

- `ghcr.io/automatiabcn/abs-backend:1.0.3` (sha256:459bb68e9ad8b6...)
- `ghcr.io/automatiabcn/abs-landing:1.0.3` (sha256:8c51aca0d591cf...)
- Both carry the same digest as `:latest`; multi-platform OCI index + cosign
  keyless attestation.

### CI status (post-v1.0.3 push)

| Workflow | Run id | Conclusion |
|----------|--------|------------|
| Release | 25968244147 | success (publish-images + cosign) |
| SBOM Generation | 25968244153 | success |
| CI Postgres (RLS) | 25968243828 | success |
| CodeQL Advanced | 25968243837 | success |
| docs | 25968243819 | failure (mike duplicate) |

### Pytest

- 2171 passed, 24 skipped, 3 deselected (SQLite baseline preserved)
- CI Postgres (RLS) 7/7 GREEN, independent of module order

### Customer upgrade

```
# Existing v1.0.x customer .env update
ABS_VERSION=1.0.3
ABS_GHCR_NAMESPACE=automatiabcn

docker compose -f infra/docker-compose.customer.yml pull
docker compose -f infra/docker-compose.customer.yml up -d
curl -sf https://${ABS_PUBLIC_HOSTNAME}/healthz
curl -sf https://${ABS_PUBLIC_HOSTNAME}/readyz
```

Customers who want to stay on the previous `enzoemir1` namespace can keep it
pinned with `ABS_GHCR_NAMESPACE=enzoemir1`.

## 1.0.1 (2026-05-14) — Hot-fix patch

Closes the 4 P0 + 6 P1 findings of the customer E2E audit, plus a customer
onboarding incident from the first deployment.

### Fixes — P0 (4/4)

- Setup wizard HTML now matches the Turkish copy byte-exactly (18+ terms: Next,
  Admin Account, Password, License Key, Finish Setup, …).
- Cascade fallback: 5 user-facing messages restored byte-exactly (for example
  the "all providers are temporarily failing; please try again" message).
- Fail-closed restore — the `/admin/*` and `/panel/*` SSR layouts probe the
  backend `/healthz`; on failure they redirect to
  `/login?reason=backend-unreachable` with a Turkish banner.
- Customer compose defaults to Postgres 16 + RLS (SQLite becomes legacy opt-in);
  the entrypoint gates on `alembic upgrade head`.

### Fixes — P1 (6/6)

- `/panel/{path}` → `/admin/{path}` 308 catch-all redirect.
- `daily_cost` MCP tool IndexError → graceful 0.0 fallback.
- Cascade with all 6 providers down now returns a structured HTTP 503
  (Retry-After 60s) from a pre-flight provider probe, instead of a silent 200 SSE.
- Caddyfile.customer `@backend` pattern gained `/me/*` (GDPR self-service
  endpoints).
- Image tag 1.0.0 → 1.0.1.
- `/auth/login` rate limited to 5/min (brute-force guard).

### Customer onboarding

- `scripts/build_customer_pkg.sh` — single-file tar.gz package builder; guards
  the REQUIRED files; excludes `__pycache__`.
- `scripts/customer_onboard.sh` — packages the `./scripts` host mount target
  (email-cron mounts `./scripts:/app/infra/scripts:ro` in compose); the email
  template spells out the single-file `tar -xzvf` flow.

### CI / regression

- `tests/test_turkce_byte_exact_blanket.py` (4) — byte-exact Turkish gate.
- `tests/test_2n_customer_compose_postgres.py` (8) — compose schema + alembic
  boot gate.
- `tests/test_2n_customer_pkg_mount_audit.py` (7) — mount completeness.
- Backend pytest baseline preserved (2143 + the new tests).

## 1.0.0 (2026-05-11) — First production release · BUSL-1.1

ABS Server **v1.0.0** — first production-ready release, source-available
under [Business Source License 1.1](../LICENSE). Change Date 2030-05-07,
Change License Apache 2.0.

### Highlights since rc1

- **6-provider cascade** with circuit breaker — Anthropic + Groq + Cerebras
  + Gemini + Cloudflare + Cohere (hexagonal restructure, pact contract tests,
  nightly regression).
- **123 MCP tools** across code, RAG, judge ML, fullstack, billing,
  observability, marketplace, compliance (was 107 in early rc).
- **Plugin marketplace** with cosign verification + Docker sandbox +
  Cerbos pre-filter + Next.js admin UI.
- **NL workflow builder** — natural-language → JSON synthesizer +
  2-stage validator + canvas.
- **Free-tier hybrid promise** — Claude quota discipline + paid-SaaS
  opt-in only + Anthropic policy compliance.
- **License + IP hardening** — JWT RS256, hardware fingerprint, phone-home
  with 7-day grace, Cython-compiled verifier.
- **Image-only customer distribution** — ghcr.io compose with source
  strip in the production stage (Cython gate verified across 1.0.0-rc2..rc8).
- **i18n EN/TR/ES** — landing, admin, customer portal, 24 email templates,
  /panel/* + /404 in three locales.
- **Lighthouse 100/100/100/100** desktop + slow-3g accessibility.
- **Test corpus 2065 passing** (pytest backend) + 53 vitest + 41 Playwright
  + 8 axe-core a11y — zero failure across CI green.

### Ship integrity reconciliation

Images for `1.0.0-rc9`, `1.0.0-rc10` and `1.0.0-rc11` were shipped to GHCR, but
the matching git tags never reached `origin`. This release reconciles the gap:

- `v1.0.0-rc9` retro-tagged at commit `d225a1c` (CodeQL prod fix x13 + dynamic
  imports + commit signing)
- `v1.0.0-rc10` retro-tagged at commit `9e0d837` (Gemini header-auth + URL
  sanitizer + CodeQL config + lighthouse slow-3g a11y)
- `v1.0.0-rc11` retro-tagged at commit `10868d6` (NOTICE.md + trademarks +
  license metadata + SBOM CI + heartbeat privacy doc)
- `v1.0.0` — first production GA tag, with SBOM (CycloneDX) + cosign keyless
  signature attached via release.yml.

`scripts/release.sh` now mandates a
`git ls-remote --tags origin | grep v${VERSION}` verification gate; no future RC
ships with a silent tag-push failure.

### Final readiness deltas

- release.sh tag-push verification gate.
- rc9/rc10/rc11 retroactive git tags + GitHub Release notes.
- docs workflow: phantom `mkdocs-algolia-docsearch` removed (the PyPI package
  never existed); validation tolerance + mike-only deps.
- License Detection workflow no longer expects an upstream `bsl-1.1` Licensee
  template that does not exist; replaced with body-shape verification.
- README "GitHub Other / NOASSERTION" disclosure (the Licensee gem does not
  bundle BUSL-1.1; documented as an upstream gap).
- CodeQL default-setup → advanced workflow with a config file + matrix python /
  javascript-typescript.
- Branch protection on main with 7 required status checks (CodeQL python + ts,
  Perf Budget lighthouse + bundlewatch + web-vitals, Lighthouse Nightly desktop
  + slow-3g).
- All production CodeQL alerts resolved, or dismissed with a per-alert
  documented rationale (no mass-dismiss).
- All Dependabot alerts patched or closed with a rationale.
- `v1.0.0` git tag + SBOM (CycloneDX) + cosign keyless + multi-arch Docker
  images (linux/amd64 + linux/arm64) + GitHub Release.
- README + CHANGELOG + CUSTOMER_USER_GUIDE final review; README badges
  refreshed (tests 2065, MCP tools 123, CI + CodeQL workflow badges, "Made in
  Barcelona").

The BGE-M3 default embedder flip is deferred to a later release.

---

## 1.0.0-rc1 (2026-04-28) — QA + 3D Hero

### 3D Hero Scene
- `core/landing/components/HeroScene3D.tsx`: React Three Fiber canvas (central icosahedron orb + 24 Fibonacci network nodes + 600-particle inward flow).
- `HeroSvgFallback.tsx` for mobile / `prefers-reduced-motion` users.
- `HeroVisual.tsx` gate decides 3D vs SVG via `matchMedia` (defensive against jsdom).
- Lazy-loaded with `next/dynamic({ ssr: false })` so three.js stays out of the initial document.
- 53/53 vitest, 23/23 Playwright, 8/8 axe-core a11y green.

### Playwright Bug-Hunt
- New `playwright.config.ts` (chromium-desktop + chromium-mobile, autobooted dev server).
- 23 tests: routes (status + console-error), axe-core a11y (WCAG 2 AA), responsive (mobile horizontal-scroll guard).
- Fixed: `/beta` form fields gained `text-slate-900 placeholder:text-slate-400` (contrast was 1.04; now WCAG 2 AA).
- `npm run test:e2e` and `test:e2e:headed` scripts.

### Real SaaS Backends
- Recall.ai `/api/v1/bot[/<id>]` httpx client (schedule / status / cancel).
- Deepgram `/v1/listen` httpx client with diarized-word parsing.
- ElevenLabs `/v1/text-to-speech/<voice>` httpx client (Multilingual v2, mp3 output).
- Gmail OAuth refresh + REST list / draft / send / label without `googleapiclient` SDK.
- 7 respx-mocked tests + 1 updated import test.

### Route 404
- Root cause: stale `.next/` cache after `/pricing` was added.
- 9-test Playwright route suite (status 200 + non-empty body + no console error).
- New `docs/troubleshooting.md` section.

### P0 Security Fix
- 2 SQL injection findings annotated `# nosec B608` with proof of safety (server-generated `?` placeholders).
- 1 SQL injection strengthened with double-validation + 4 KiB length cap.
- 9 dev secrets gated by `assert_production_safe()` — boot fails fast in `env=prod` if any default leaks.
- Full `core/backend/.env.example` inventory.
- 4 SQLModel ORM call sites confirmed as ORM (not subprocess); ignored at scanner config.

## 0.1.0 (2026-04-27) — Documentation Site

### Documentation Site
- MkDocs Material build, navigation, search, brand-aligned.
- 6 new docs: index, setup-guide, api-reference (auto-generated, 104 tools), troubleshooting, faq, CHANGELOG.
- Build script + GitHub Actions workflow.

### Onboarding Email Sequence (2026-04-27)
- 5 email templates (welcome, walkthrough, first_success, expiry_warning, recovery).
- `EmailQueue` SQLModel + scheduler (schedule, tick, retry with exponential backoff, unsubscribe JWT).
- Webhook hook → 4 emails auto-scheduled on `checkout.session.completed`.
- First-success middleware trigger.
- Cron worker docker service `email-cron` (every 5min).
- MCP tool `email_queue_status`.
- Unsubscribe endpoint `GET /v1/email/unsubscribe?token=...`.
- 18 new tests, 1 new MCP tool.

### Landing Page Premium (2026-04-27)
- Hero premium SVG illustration (isometric cube stack, brand gradient).
- Pricing CTA → /api/checkout POST + Stripe redirect.
- FAQ 8 → 12 (vault, refund, GDPR, open source).
- Quotes section (3 testimonials), Demo section (Loom iframe lazy).
- ManageModal — Stripe Customer Portal modal.
- Privacy / Terms / Refund pages (GDPR compliant, EU 2011/83/EU).
- Lighthouse 100/100 desktop+mobile.
- 17 vitest (8 files).

### Stripe Live + Customer Portal + First Customer Playbook (2026-04-26)
- `WebhookEvent` table + idempotency (claim_event / mark_processed).
- `POST /v1/billing/portal` Stripe Customer Portal session.
- `setup_stripe_products.py` argparse refactor (`--mode test|live` + safeguard + `--dry-run`).
- MCP tool `billing_status` (Stripe products + revenue + license counts + recent events).
- `docs/billing-runbook.md` + `docs/first-customer-playbook.md`.
- 22 new tests (270 → 292), 1 new MCP tool (102 → 103).

### Symbol Graph + RAG Hybrid + ML Persona + Tokens (2026-04-26)
- Symbol DB (SQLite + AST parser, neighbors BFS).
- RAG hybrid (BM25 + cosine fusion, alpha_semantic param).
- ML persona predict (pure-Python logistic regression, 200 epochs).
- Real token tracking (tokens_in_24h / tokens_out_24h aggregation).
- Cost estimator separates measured cost from estimated cost.
- 4 new tests, 3 new MCP tools (99 → 102).

### Panel Real Data + Manifest Signature (2026-04-25)
- `cost_estimator.py` token-aware billing.
- `learnings/store.py` JSONL append-only (24h dedup, 6 categories).
- `update/signature.py` (RSA PKCS1v15+SHA256, fail-closed).
- MCP tools `daily_cost`, `learnings_recent`, `learnings_log`.
- Watchdog deploy.sh, manifest-keys generator.

### Update Channel + Health + Breaker + Watchdog (2026-04-25)
- `update/manifest.py` 4-state (current/available/critical/unknown).
- `health/monitor.py` 60s asyncio loop.
- `cascade/persist.py` breaker state on disk.
- 6 provider YAML configs.
- Watchdog skeleton (VPS deploy ready).
- 3 new MCP tools (update_check, health_status, breaker_status).

### Encrypted Secrets Vault sops + age (2026-04-24)
- Mozilla sops + age binary integration.
- `vault/runner.py` + `cache.py` + `migration.py` + `audit.py`.
- 11-key map (Stripe + Anthropic + SMTP + provider keys).
- Plaintext .env migration (idempotent).
- MCP tool `vault_status`.

### Setup Wizard + First-Run + Email (2026-04-24)
- 6-step setup wizard (vanilla HTML/JS).
- First-run middleware (whitelist redirect to /setup).
- Email templates: license_refund, license_expired.
- MCP tool `setup_status`.

### Stripe Checkout + Demo + Gate + Refund (2026-04-23)
- `POST /v1/checkout/create-session` (3 SKU mapping).
- Demo countdown 14 days.
- MCP gate (`mcp_require_license` toggle).
- Webhook handlers: `charge.refunded` + `customer.subscription.deleted`.
- MCP tools `license_status`, `demo_status`.

### Workflow + MLX + Judge + RAG + Dockerfile (2026-04-22)
- `WorkflowSession` (no-op when `workflow_durable=False`).
- MLX provider HTTP bridge (port 11436).
- Judge persona training (`train_persona`, `persona_status`, `reset_persona`).
- RAG chunker (Python AST + Markdown heading + char fallback).
- Dockerfile multi-stage (builder + runtime).
- MCP tools `judge_persona_*`.

## 0.0.x (up to 2026-04-20) — Production Feature Parity

Final baseline before the 0.1.0 feature line: 89 MCP tools, 118 tests.
