# Changelog

Versiyon kayıtları — her task tek satır, tarih + delta.

## 1.0.6 (2026-05-25) — 5-tur denetim hardening (11 fix)

Opus full-system audit (5 lens: render/fonksiyon, tasarım-niyeti, güvenlik,
dayanıklılık, E2E). Düzeltmeler:
- **cascade default FREE-FIRST** — `PROVIDER_ORDER_DEFAULT` (Groq→…→Anthropic
  son fallback), `ABS_HYBRID_TIER_PROMISE`'e hizalandı; chat + cascade + workflows
  artık ücretsiz-yol default. UI `providers_status` aynı sıraya geldi.
- **graph NL→Cypher** `cascade_call` (yok) → `call_with_cascade` + JSON-fence strip.
- **versiyon tek-kaynak** `settings.version` (ABS_VERSION) → status/main/footer/pyproject.
- **configs.py `_default_dir()`** `parents[4]` IndexError guard (env'siz cold-deploy crash).
- **graph/cypher boş** 500→422, **graph/nl-query boş intent** 502→422.
- **panel cascade** `providers_active` + `timeseries` döndürüyor (panel "0" bug).
- **admin/usage** canlı DB `usage_log` merge + `cerebras` FREE_PROVIDERS'e eklendi.
- **RAG** `GET /v1/rag/documents` + `qc.list_documents` (sayfa depoyu gösterir).
- Kota header overlap (flex-wrap), /admin/audit React #418 (timeZone pin).

Güvenlik (R3) temiz: auth-required sweep 401, tenant izolasyon, rate-limit 429,
destructive cypher 400, forged MCP token 401, secret sızıntısı yok. Bilinen açık
uçlar: admin paneli i18n değil (TR-only), GitHub Smart Link placeholder OAuth.

## 1.0.4 (2026-05-16) — Sprint 2N.3 docs alias split (v1.0.3 yellow → green)

Tek FAZ: `docs.yml` `MIKE_VERSION` artık `github.ref_name`'den türetiliyor
(tag → `v1.0.x`, main push → `main`); alias `latest` ayrı kanaldan
güncelleniyor. Önceki 5 ardışık fail'in (run 25968243819 + öncekiler)
kök neden olan version+alias çakışması kapandı. docs workflow ilk kez
GREEN; `docs.automatiabcn.com/v1.0.4/` ve `/` (alias) canlı. Merge
commit `f433dcb`, run 25968714499.

Tüm v1.0.3 değişiklikleri taşındı; runtime image içeriği aynı (backend
+ landing yeniden push edildi `:1.0.4` + `:latest` tag'leriyle). Müşteri
upgrade için tek değişiklik `.env` içinde `ABS_VERSION=1.0.4`.

Önceki entry için bkz. v1.0.3.

## 1.0.3 (2026-05-16) — Sprint 2N.2 hot-patch (release GA, docs gap open)

v1.0.1 ve v1.0.2 release'lerinde release.yml workflow yeşil görünmesine
rağmen ghcr.io'da müşteri image'ı YOKTU — smebes upgrade ve Pilot Batch
2 HTTP 404 ile bekliyordu. 2N.1 + 2N.2 hot-patch döngüsü 4 + 4 gap'i
kapattı; v1.0.3 ilk kez gerçek image-ship.

**Açık kalan tek gap:** docs / mike deploy hâlâ `duplicated version and
alias` hatası veriyor (run 25968243819). Sprint 2N.3 single-fix patch
chain ile kapatılacak (`docs.yml` resolve-version step + alias/version
split). docs.automatiabcn.com bu yüzden v1.0.3 sayfasını yansıtmıyor;
GitHub Release notları + bu CHANGELOG kanonik.

### Fixes — Sprint 2N.1 (3)

- **2N.1-A** Postgres CI: oauth_clients migration `BOOLEAN DEFAULT 0`
  → `DEFAULT FALSE`; alembic revision id 36 char → 24 char (varchar(32)
  alembic_version sınırı); env.py legacy revision rewrite shim ile
  SQLite müşteri geriye uyumlu.
- **2N.1-B** release.yml `publish-images` job eklendi (cosign-sign
  hiçbir image yokken imzalıyordu); matrix backend+landing build+push
  + provenance + SBOM + cosign keyless chain.
- **2N.1-C** docs mike deploy idempotent ön deneme (2N.2'de iyileştirildi,
  2N.3'te kapatılacak — `grep` regex `[latest]` bracket eşleşmiyor).

### Fixes — Sprint 2N.2 (3 kapalı + 1 kısmi)

- **2N.2-A** Backend Dockerfile pubkey path → `app/update/manifest_pubkey.pem`
  (sibling `core/backend/manifest_pubkey.pem` `*.pem` gitignored, CI
  checkout missing). Release backend GREEN.
- **2N.2-B** GHCR namespace `enzoemir1` → `automatiabcn` (workflow
  GITHUB_TOKEN cross-account push edemiyor; `permission_denied:
  installation does not exist`). Customer compose `ABS_GHCR_NAMESPACE`
  env var ile parametrize, default `automatiabcn`. Release landing GREEN.
- **2N.2-C** docs mike pre-delete koşulsuz hale getirildi. Kısmi:
  `mike delete latest` alias'ı kaldırıyor ama version'ı bırakıyor;
  sonraki deploy aynı duplicate hatasına düşüyor. Sprint 2N.3'e devredildi.
- **2N.2-D** CI Postgres RLS 5 test fail — iki rol modeli (`abs_app`
  SUPERUSER alembic için, `abs_app_rls` NOSUPERUSER NOBYPASSRLS data
  ops için), NullPool ile GUC leak fix, downgrade test finally'de LOGIN
  + grants restore. CI Postgres 7/7 GREEN.

### Infra ship (v1.0.3)

- `ghcr.io/automatiabcn/abs-backend:1.0.3` (sha256:459bb68e9ad8b6...)
- `ghcr.io/automatiabcn/abs-landing:1.0.3` (sha256:8c51aca0d591cf...)
- Her ikisi `:latest` aynı digest; multi-platform OCI index + cosign
  keyless attestation.

### CI status (post-v1.0.3 push)

| Workflow | Run id | Conclusion |
|----------|--------|------------|
| Release | 25968244147 | success (publish-images + cosign) |
| SBOM Generation | 25968244153 | success |
| CI Postgres (RLS) | 25968243828 | success (FAZ D verify) |
| CodeQL Advanced | 25968243837 | success |
| docs | 25968243819 | failure (mike duplicate; 2N.3) |

### Pytest

- 2171 passed, 24 skipped, 3 deselected (SQLite baseline korundu)
- CI Postgres (RLS) 7/7 GREEN, modül sırası bağımsız

### Customer upgrade (founder one-paste)

```
# Existing v1.0.x customer .env update
ABS_VERSION=1.0.3
ABS_GHCR_NAMESPACE=automatiabcn

docker compose -f infra/docker-compose.customer.yml pull
docker compose -f infra/docker-compose.customer.yml up -d
curl -sf https://${ABS_PUBLIC_HOSTNAME}/healthz
curl -sf https://${ABS_PUBLIC_HOSTNAME}/readyz
```

Pre-2N.2 `enzoemir1` namespace'inde kalmak isteyen müşteriler
`ABS_GHCR_NAMESPACE=enzoemir1` ile pin'li çalışabilir; founder
`GHCR_USER=enzoemir1 ./scripts/release.sh 1.0.3` ile manuel dual
publish yapabilir.

## 1.0.1 (2026-05-14) — Sprint 2N hot-fix patch

Sprint 2M Customer E2E Audit'in 4 P0 + 6 P1 bulgusu + smebes (ilk pilot)
customer onboarding incident'ı kapatıldı. Cert footer 🟡 RC → 🟢 GREEN
eligible; Pilot Batch 2 gate açıldı.

### Fixes — P0 (4/4)

- **#2M-003** Setup wizard HTML Türkçe byte-exact (18+ kelime: İleri,
  Yönetici Hesabı, Şifre, Lisans Anahtarı, Kurulumu Bitir, …).
- **#2M-017** Cascade fallback 5 mesaj byte-exact ("Tüm sağlayıcılar
  geçici hata verdi; lütfen tekrar deneyin." vb.).
- **#2M-025** UAT-009 fail-closed restore — `/admin/*` ve `/panel/*` SSR
  layout'ları backend `/healthz` probe yapar; fail → `/login?reason=
  backend-unreachable` Türkçe banner.
- **#2M-026** Customer compose Postgres 16 + Sprint 2K RLS varsayılan
  (SQLite legacy opt-in); entrypoint `alembic upgrade head` gate'i.

### Fixes — P1 (6/6)

- **#2M-009** `/panel/{path}` → `/admin/{path}` 308 catch-all redirect.
- **#2M-014** `daily_cost` MCP tool IndexError → graceful 0.0 fallback.
- **#2M-018** Cascade 6-down structured HTTP 503 (Retry-After 60s) —
  silent 200 SSE yerine pre-flight provider probe.
- **#2M-020** Caddyfile.customer `@backend` pattern'ına `/me/*` eklendi
  (KVKK self-service endpoints).
- **#2M-023** Image tag 1.0.0 → 1.0.1 (founder `v1.0.1` push gate).
- **#2M-024** `/auth/login` 5/min rate limit (UAT-041 brute force guard).

### Customer onboarding (smebes lesson 18)

- `scripts/build_customer_pkg.sh` — tek-dosya tar.gz paket üretici;
  REQUIRED dosya guard'ı; `__pycache__` exclude.
- `scripts/customer_onboard.sh` — `./scripts` host mount target paketlenir
  (email-cron compose'da `./scripts:/app/infra/scripts:ro` mount eder);
  email template tek-dosya `tar -xzvf` flow'unu açıkça anlatır.

### CI / regression

- `tests/test_turkce_byte_exact_blanket.py` (4) — Lesson 11 byte-exact gate.
- `tests/test_2n_customer_compose_postgres.py` (8) — compose schema +
  alembic boot gate.
- `tests/test_2n_customer_pkg_mount_audit.py` (7) — mount completeness.
- Backend pytest baseline korundu (Sprint 2K + 2M = 2143 + Sprint 2N
  yeni testler).

## 1.0.0 (2026-05-11) — First production release · BUSL-1.1

ABS Server **v1.0.0** — first production-ready release, source-available
under [Business Source License 1.1](../LICENSE). Change Date 2030-05-07,
Change License Apache 2.0.

### Highlights since rc1

- **6-provider cascade** with circuit breaker — Anthropic + Groq + Cerebras
  + Gemini + Cloudflare + Cohere (Sprint 19 hexagonal restructure, pact
  contract tests, nightly regression).
- **123 MCP tools** across code, RAG, judge ML, fullstack, billing,
  observability, marketplace, compliance (was 107 in early rc).
- **Plugin marketplace** with cosign verification + Docker sandbox +
  Cerbos pre-filter + Next.js admin UI (Sprint 19 T-S01).
- **NL workflow builder** — natural-language → JSON synthesizer +
  2-stage validator + canvas (Sprint 19 T-S03).
- **Free-tier hybrid promise** — Claude quota discipline + paid-SaaS
  opt-in only + Anthropic policy compliance (Sprint 20 T-F01..F05).
- **License + IP hardening** — JWT RS256, hardware fingerprint, phone-home
  with 7-day grace, Cython-compiled verifier (Q12 IP-Hardening R1..R3).
- **Image-only customer distribution** — ghcr.io compose with source
  strip in production stage (R3 onboarding ghcr PAT, 1.0.0-rc2..rc8
  Cython gate verified).
- **i18n EN/TR/ES** — landing, admin, customer portal, 24 email templates,
  /panel/* + /404 in three locales (Sprint 17 + Sprint 19 polish).
- **Lighthouse 100/100/100/100** desktop + slow-3g accessibility (Sprint
  17 + Sprint 2E ITEM C).
- **Test corpus 2065 passing** (pytest backend) + 53 vitest + 41 Playwright
  + 8 axe-core a11y — zero failure across CI green.

### Ship integrity reconciliation (Sprint 2G)

Sprints 2D / 2E / 2F shipped images to GHCR for `1.0.0-rc9`, `1.0.0-rc10`,
`1.0.0-rc11` but the corresponding git tags never reached `origin`. Sprint
2G (ITEM 1 audit + ITEM 2 retroactive tag) reconciled the gap:

- `v1.0.0-rc9` retro-tagged at commit `d225a1c` (Sprint 2D — CodeQL prod
  fix x13 + dynamic imports + commit signing)
- `v1.0.0-rc10` retro-tagged at commit `9e0d837` (Sprint 2E — Gemini
  header-auth + URL sanitizer + CodeQL config + lighthouse slow-3g a11y)
- `v1.0.0-rc11` retro-tagged at commit `10868d6` (Sprint 2F — NOTICE.md
  + trademarks + license metadata + SBOM CI + heartbeat privacy doc)
- `v1.0.0` at the Sprint 2G head — first production GA tag with SBOM
  (CycloneDX) + cosign keyless signature attached via release.yml.

Root cause + Lesson 15 revision documented at
`_agent-tasks/SHIP_INTEGRITY_AUDIT_2026-05-11.md`. `scripts/release.sh`
patched to mandate a `git ls-remote --tags origin | grep v${VERSION}`
verification gate; no future RC ships with a silent tag-push failure.

### Sprint 2G — final readiness deltas

- **ITEM 1** — release.sh tag-push verification gate + audit doc.
- **ITEM 2** — rc9/rc10/rc11 retroactive git tag + GitHub Release notes.
- **ITEM 3** — docs workflow phantom `mkdocs-algolia-docsearch` removed
  (PyPI package never existed); validation tolerance + mike-only deps.
- **ITEM 4** — License Detection workflow no longer expects an upstream
  `bsl-1.1` Licensee template that does not exist; replaced with
  body-shape verification.
- **ITEM 5** — README "GitHub Other / NOASSERTION" disclosure (Licensee
  gem doesn't bundle BUSL-1.1; documented as upstream gap).
- **ITEM 6** — CodeQL default-setup → advanced workflow with config-file
  + matrix python / javascript-typescript.
- **ITEM 7** — branch protection main with 7 required status checks
  (CodeQL python + ts, Perf Budget lighthouse + bundlewatch + web-vitals,
  Lighthouse Nightly desktop + slow-3g).
- **ITEM 9** — all production CodeQL alerts resolved or per-alert
  documented dismissal (Lesson 11 — no mass-dismiss).
- **ITEM 10** — all Dependabot alerts patched or rationale closed.
- **ITEM 11** — `v1.0.0` git tag + SBOM (CycloneDX) + cosign keyless +
  multi-arch Docker images (linux/amd64 + linux/arm64) + GitHub Release.
- **ITEM 12** — README + CHANGELOG + CUSTOMER_USER_GUIDE final review,
  README badges refreshed (tests 2065, MCP tools 123, CI + CodeQL
  workflow badges, "Made in Barcelona").
- **ITEM 13** — Sprint 2G report + customer pilot plan
  (`_agent-tasks/CUSTOMER_PILOT_PLAN.md`).
- **ITEM 14** — repo image audit: About + Topics + social preview +
  Discussions + branch cleanup + 4 → 0 open issue.

ITEM 8 (BGE-M3 default embedder flip) remains gated behind a founder
APPROVED trailer; carried forward to Sprint 21.

---

## 1.0.0-rc1 (2026-04-28) — Sprint 17 QA + 3D Hero

### T-Q05 — 3D Hero Scene
- `core/landing/components/HeroScene3D.tsx`: React Three Fiber canvas (central icosahedron orb + 24 Fibonacci network nodes + 600-particle inward flow).
- `HeroSvgFallback.tsx` for mobile / `prefers-reduced-motion` users.
- `HeroVisual.tsx` gate decides 3D vs SVG via `matchMedia` (defensive against jsdom).
- Lazy-loaded with `next/dynamic({ ssr: false })` so three.js stays out of the initial document.
- 53/53 vitest, 23/23 Playwright, 8/8 axe-core a11y green.

### T-Q04 — Playwright Bug-Hunt
- New `playwright.config.ts` (chromium-desktop + chromium-mobile, autobooted dev server).
- 23 tests: routes (status + console-error), axe-core a11y (WCAG 2 AA), responsive (mobile horizontal-scroll guard).
- BUG-Q4-01 fixed: `/beta` form fields gained `text-slate-900 placeholder:text-slate-400` (was 1.04 contrast; now WCAG 2 AA).
- Bug report: `docs/qa/bug_report_2026-04-28.md`.
- `npm run test:e2e` and `test:e2e:headed` scripts.

### T-Q03 — Real SaaS Backends
- Recall.ai `/api/v1/bot[/<id>]` httpx client (schedule / status / cancel).
- Deepgram `/v1/listen` httpx client with diarized-word parsing.
- ElevenLabs `/v1/text-to-speech/<voice>` httpx client (Multilingual v2, mp3 output).
- Gmail OAuth refresh + REST list / draft / send / label without `googleapiclient` SDK.
- 7 respx-mocked tests + 1 updated import test.

### T-Q02 — Route 404
- Root cause: stale `.next/` cache after T-061 added `/pricing`.
- 9-test Playwright route suite (status 200 + non-empty body + no console error).
- New `docs/troubleshooting.md` section.

### T-Q01 — P0 Security Fix
- 2 SQL injection findings annotated `# nosec B608` with proof of safety (server-generated `?` placeholders).
- 1 SQL injection strengthened with double-validation + 4 KiB length cap.
- 9 dev secrets gated by `assert_production_safe()` — boot fails fast in `env=prod` if any default leaks.
- Full `core/backend/.env.example` inventory.
- 4 SQLModel ORM call sites confirmed as ORM (not subprocess); ignored at scanner config.

## 0.1.0 (2026-04-27) — Documentation Site

### Task 020 — Documentation Site
- MkDocs Material build, navigation, search, brand-aligned.
- 6 yeni doc: index, setup-guide, api-reference (otomatik gen 104 tool), troubleshooting, faq, CHANGELOG.
- Build script + GitHub Actions workflow.

### Task 019 — Onboarding Email Sequence (2026-04-27)
- 5 email template (welcome, walkthrough, first_success, expiry_warning, recovery).
- `EmailQueue` SQLModel + scheduler (schedule, tick, retry exponential backoff, unsubscribe JWT).
- Webhook hook → 4 email auto-schedule on `checkout.session.completed`.
- First-success middleware trigger.
- Cron worker docker service `email-cron` (every 5min).
- MCP tool `email_queue_status`.
- Unsubscribe endpoint `GET /v1/email/unsubscribe?token=...`.
- 18 yeni test, 1 yeni MCP tool.

### Task 018 — Landing Page Premium (2026-04-27)
- Hero premium SVG illustration (isometric cube stack, brand gradient).
- Pricing CTA → /api/checkout POST + Stripe redirect.
- FAQ 8 → 12 (vault, refund, GDPR, açık kaynak).
- Quotes section (3 testimonial), Demo section (Loom iframe lazy).
- ManageModal — Stripe Customer Portal modal (017 backend).
- Privacy / Terms / Refund pages (GDPR uyumlu, AB 2011/83/EU).
- Lighthouse 100/100 desktop+mobile.
- 17 vitest (8 dosya).

### Task 017 — Stripe Live + Customer Portal + First Customer Playbook (2026-04-26)
- `WebhookEvent` table + idempotency (claim_event / mark_processed).
- `POST /v1/billing/portal` Stripe Customer Portal session.
- `setup_stripe_products.py` argparse refactor (`--mode test|live` + safeguard + `--dry-run`).
- MCP tool `billing_status` (Stripe products + revenue + license counts + recent events).
- `docs/billing-runbook.md` + `docs/first-customer-playbook.md`.
- 22 yeni test (270 → 292), 1 yeni MCP tool (102 → 103).

### Task 016 — Symbol Graph + RAG Hybrid + ML Persona + Tokens (2026-04-26)
- Symbol DB (SQLite + AST parser, neighbors BFS).
- RAG hybrid (BM25 + cosine fusion, alpha_semantic param).
- ML persona predict (pure-Python logistic regression, 200 epoch).
- Real token tracking (tokens_in_24h / tokens_out_24h aggregation).
- Cost estimator gerçek/tahmini ayrımı.
- 4 yeni test, 3 yeni MCP tool (99 → 102).

### Task 015 — Panel Real Data + Manifest Signature (2026-04-25)
- `cost_estimator.py` token-aware billing.
- `learnings/store.py` JSONL append-only (24h dedup, 6 categories).
- `update/signature.py` (RSA PKCS1v15+SHA256, fail-closed).
- MCP tools `daily_cost`, `learnings_recent`, `learnings_log`.
- Watchdog deploy.sh, manifest-keys generator.

### Task 014 — Update Channel + Health + Breaker + Watchdog (2026-04-25)
- `update/manifest.py` 4-state (current/available/critical/unknown).
- `health/monitor.py` 60s asyncio loop.
- `cascade/persist.py` breaker state disk.
- 6 provider YAML configs.
- Watchdog skeleton (Hetzner deploy ready).
- 3 yeni MCP tool (update_check, health_status, breaker_status).

### Task 013 — Encrypted Secrets Vault sops + age (2026-04-24)
- Mozilla sops + age binary integration.
- `vault/runner.py` + `cache.py` + `migration.py` + `audit.py`.
- 11-key map (Stripe + Anthropic + SMTP + provider keys).
- Plaintext .env migration (idempotent).
- MCP tool `vault_status`.

### Task 012 — Setup Wizard + First-Run + Email (2026-04-24)
- 6-step setup wizard (vanilla HTML/JS).
- First-run middleware (whitelist redirect to /setup).
- Email templates: license_refund, license_expired.
- MCP tool `setup_status`.

### Task 011 — Stripe Checkout + Demo + Gate + Refund (2026-04-23)
- `POST /v1/checkout/create-session` (3 SKU mapping).
- Demo countdown 14 days.
- MCP gate (`mcp_require_license` toggle).
- Webhook handlers: `charge.refunded` + `customer.subscription.deleted`.
- MCP tools `license_status`, `demo_status`.

### Task 010 — Workflow + MLX + Judge + RAG + Dockerfile (2026-04-22)
- `WorkflowSession` (no-op when `workflow_durable=False`).
- MLX provider HTTP bridge (port 11436).
- Judge persona training (`train_persona`, `persona_status`, `reset_persona`).
- RAG chunker (Python AST + Markdown heading + char fallback).
- Dockerfile multi-stage (builder + runtime).
- MCP tools `judge_persona_*`.

## 0.0.x (2026-04-20'ye kadar) — Production Feature Parity

010 öncesi: 89 MCP tool, 118 test, 010-019 kapsamına geçişten önceki son baseline.

---

Detay için ilgili task summary'leri: `_agent-tasks/completed/0XX-*-summary.md`.
