# Changelog

Versiyon kayıtları — her task tek satır, tarih + delta.

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
