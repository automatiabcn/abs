# Customer Journey Test — Checklist

> Pairs with `scripts/seed_demo_tenant.py` and `scripts/purge_demo_tenant.py`.
> Total budget: 2–3 hours, Playwright headed, demo tenant `demo-acme`.

## Pre-flight

- [ ] `python scripts/seed_demo_tenant.py` → expect `WROTE … fingerprint=…` (or `UNCHANGED`).
- [ ] `python scripts/seed_demo_tenant.py` again → expect `UNCHANGED` (idempotency check).
- [ ] `cp .env.demo .env.local` and replace each `replace-with-*` placeholder.
- [ ] `docker compose up -d` (Cerbos PDP, Qdrant, NATS, backend, landing).
- [ ] `cerbos compile cerbos/policies` returns `63 OK`.
- [ ] `pytest -q` baseline shows 1266+ passing before journey.

## Phase 1 — Landing → Pricing → Sign-up

- [ ] `/` renders below 1.0 s LCP (Lighthouse staged run acceptable).
- [ ] Switch language EN → TR → ES; Pricing tier copy localises correctly.
- [ ] Click `Get Started` → Stripe Checkout TEST mode (`pk_test_…` only).
- [ ] Complete Stripe TEST card 4242 4242 4242 4242 → returns to `/success`.
- [ ] Inbox receives the welcome email (mock SMTP captured by MailHog/etc.).

## Phase 2 — Onboarding Wizard

- [ ] Login as `demo@acme.test` (admin role).
- [ ] Wizard renders 5 steps; complete each (workspace name, team size, locale, integrations toggle, finish).
- [ ] `i18n` strings localise on each step.
- [ ] Tooltip / help-icon visible on every step (a11y axe scan green).

## Phase 3 — Plugin Marketplace

- [ ] `/admin/marketplace` shows the 5 reference plugins (vLLM, Bedrock, SharePoint, Slack, Notion).
- [ ] Search "rag" filters to `sharepoint-rag` + `slack-thread-rag`.
- [ ] Click `Install` on `notion-sync` → permission review modal opens.
- [ ] Modal lists exactly: network egress hosts, secrets, mounts, cpu/mem, scope.
- [ ] Click `Approve & Install` → modal closes (no real install yet, sandbox audit gate still required).

## Phase 4 — RAG + Workflow Builder

- [ ] `/admin/workflow-builder` opens with the canvas + chat panel.
- [ ] Cost preview shows the SAMPLE_WORKFLOW estimate (e.g., `$0.04`).
- [ ] Type intent: *"Summarise our handbook and email the team"*.
- [ ] Click `Synthesize` → canvas updates with 4–6 nodes including an `abs.cerbos_check` and a HITL.
- [ ] Click `Dry run` → status flips to `Running` then `Success`.
- [ ] Click `Save` → toast confirms persistence.

## Phase 5 — Meetings & Action Items (free tier — meetily + Coqui)

- [ ] `ABS_RECALL_BACKEND=local` (default) — confirm `bot_recall` opt-in guard refuses without `ABS_RECALL_ENABLED=true`.
- [ ] Drop `mtg-001.wav` into `${ABS_MEETING_RECORDINGS_DIR}` and call `accept_upload(...)`.
- [ ] WhisperX local backend produces a transcript; `wer(reference, hypothesis) < 0.10`.
- [ ] `abs.action_extract` produces ≥2 action items with assignees `Esra`/`Mert`.
- [ ] Each action item creates a Linear ticket via `abs.linear_create_ticket` (project_owner gate).
- [ ] TTS reminder runs through Coqui (or auto-falls back to Piper) — output audio file present, `cost_usd == 0.00`.

## Phase 6 — Quality Gates + Quota Tracker

- [ ] Default config: `ABS_ANTHROPIC_ENABLED=false`. Open `/admin/usage` — Claude budget shows `0 %`.
- [ ] Run `qual_code` on a sample diff → result returns; LangFuse trace shows GPT-OSS-120B baseline (no Anthropic span).
- [ ] Run `race_code` and `cascade` workflows → 0 Anthropic spans in LangFuse.
- [ ] (Opt-in spot-check) flip `ABS_ANTHROPIC_ENABLED=true` + supply a sandbox Anthropic key, run a single Claude call, observe `quota_monitor` ledger increment + dashboard percentage move; flip back off and confirm subsequent calls fail with the opt-in guard.
- [ ] (Quota stress) `python -m pytest tests/test_quota_discipline.py::test_simulated_1m_token_run_progresses_through_thresholds -v` passes — confirms 80 % warn → 95 % block transition.

## Phase 7 — Cross-tenant Boundary Spot-check

- [ ] Create a second tenant `demo-evil`.
- [ ] As `demo-evil` member, attempt RAG query against `demo-acme` corpus → 403.
- [ ] As `demo-evil` member, attempt `abs.gmail_send` against `demo-acme` workflow node → 403.
- [ ] Cerbos audit log shows `cerbos_pre_filter_deny` entries for both attempts.

## Phase 8 — Cleanup & Audit

- [ ] `python scripts/purge_demo_tenant.py` → reports key rotation + fixture removal.
- [ ] `.audit/demo-acme-purge.log` and `.audit/demo-acme-key-rotation.log` each gain a fresh JSON line.
- [ ] Cerbos audit log shows no orphaned ALLOW entries for `demo-acme` post-purge.
- [ ] Re-run baseline `pytest -q` → 1300+ passing (post-Sprint-19 G-gates baseline).

## Sign-off

| Phase | Pass/Fail | Notes |
|-------|-----------|-------|
| 1 — Landing → Pricing → Sign-up | ☐ | |
| 2 — Onboarding wizard | ☐ | |
| 3 — Plugin marketplace | ☐ | |
| 4 — RAG + Workflow builder | ☐ | |
| 5 — Meetings & action items (free tier) | ☐ | |
| 6 — Quality gates + Quota tracker | ☐ | |
| 7 — Cross-tenant boundary | ☐ | |
| 8 — Cleanup & audit | ☐ | |

> **Manual gate:** if any FAIL is recorded, file a `qa-customer-journey` issue and pause the launch sequence.
