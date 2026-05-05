# Tester Handoff Checklist — ABS Server

## Status

Sprint Q12 closed at HEAD `dbaeca8` on branch `feat/sprint-q12-deep-quality` after 100 atomic rounds (R1–R99 + this docs alignment).

> **S11 → S12 retraction note:** S11 worker shipped this checklist at HEAD `ddfdf8c` claiming 1791 PASS / "MÜHÜRLÜ"; founder host run revealed the true full-suite state was **1735 passed / 3 failed / 17 errors** (selective subset gave a false GREEN — Q12-L19-001 4th repeat). S12 R96–R99 closed the regression and re-sealed at the canonical full-suite count below.

**Canonical pre-handoff command (single source of truth):**

```
cd core/backend
./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
```

Run this on the founder host before tagging `handoff/v1`. Expected last line:
`1755 passed, 14 skipped, 3 deselected, 0 failed, 0 errors`. The three
ignored files are network-dependent (live SaaS / live update channel) and are
deferred to staging or out-of-band.

## 1. Test Coverage Evidence

| Layer | Status | Evidence (commit / file / count) |
|-------|--------|-----------------------------------|
| Backend pytest full-suite (canonical command above) | **1755 PASS / 0 fail / 0 error / 14 skipped / 3 deselected** | HEAD `dbaeca8` (S12 R99) |
| Q12 layers FULL CLEAN | 10/10 | L17–L26 closed |
| Q11/Q10 inherited deep | CLOSED | L4 deep, L6 ZAP 0 alert, L13 fuzz 30K cron |
| Cross-browser (chromium + firefox + webkit + chromium-mobile) | 24/24 | R72 commit `64f8600` |
| Setup wizard 11-step E2E (R78) | 3/3 PASS | commit `d13588c` |
| Provider degradation matrix (R85) | 7/7 PASS | commit `d507966` |
| License JWT full lifecycle (R86) | 7/7 PASS | commit `35774cc` |
| Magic-link multi-admin (R87) | 6/6 PASS | commit `c0d1d28` |
| Final acceptance combined E2E (R91) | 1/1 PASS | commit `ddfdf8c` |
| OWASP ZAP baseline + active | 0 alert | R45+R46 |
| Hypothesis fuzz 30K weekend cron | green | R55 + R80 |
| L26 30-min long-running session | drift -9.63 MB | R37 |
| fs-scan honest score | 95+ | R79 commit `529f296` |

## 2. Production Readiness

| Item | Status | Note |
|------|--------|------|
| Helm K8s 1.27/1.28/1.29 dry-run | PASS (source) | R76 commit `6debd63` — production cluster apply gated to founder |
| DR drill spec | shipped, gated | R77 commit `cd7c745` — guard `ABS_DR_DRILL=1` |
| Cerbos production live deploy spec | spec only | R89 — founder runs helm upgrade |
| Lighthouse nightly cron | fix shipped | R82 commit `f362601` — first cron review 2026-05-09 02:00 UTC |
| Pricing audit | 0 unexplained $ | R84 — six surfaces moved to settings, tier IDs preserved as SKU keys |

## 3. Repository Hygiene

- Hardcoded $ values: **0** (R84 six-surface refactor)
- Tier IDs ("self-host", "team-5", "team-10") preserved as SKU keys
- Pilot/market/outreach references in user-facing docs: **0**
- fs-scan honest score: **95+** (R79, allowlist v5)

## 4. Founder Action Items (BLOCKED on founder, before tester handoff)

1. **Stripe products + Price IDs setup** — run `infra/scripts/setup_stripe_products.py`, capture the resulting Stripe Price IDs, set them as env vars.
2. **Env vars** — set `ABS_SEAT_PRICE_SELF_HOST`, `ABS_SEAT_PRICE_TEAM_5`, `ABS_SEAT_PRICE_TEAM_10`, `ABS_PRICE_SELF_HOST`, `ABS_PRICE_TEAM_5`, `ABS_PRICE_TEAM_10`, `ABS_REVENUE_WIDGET_MULTIPLIER` from real prices.
3. **License JWT generate** — mint a tester license via `app.licensing.generate_license(...)` and set `ABS_LICENSE_KEY` in the production env.
4. **Cerbos helm upgrade** — run on the production cluster per R89 spec, then run the 4-step verify checklist.
5. **Image rebuild + push to registry** — `docker compose -f infra/docker-compose.dev.yml build api` then push; verify CI image matches HEAD `ddfdf8c`.
6. **Lighthouse first nightly cron review** — inspect the 2026-05-09 02:00 UTC artifact at `artifacts/lighthouse/` once available.
7. **Tester handoff package** — repo URL + branch (`feat/sprint-q12-deep-quality`) + activation key + provider key list (Anthropic + Groq + Gemini + Cerebras + Cohere + Cloudflare + optional OpenRouter + vLLM).

## 5. Persistent SKIPs (intentional, founder approval gate)

- L21 destructive run — gated, 6/6 SKIPPED across S5–S10
- Mutmut local run — gated, 5/5 SKIPPED across S6–S10

## 6. Tester Hand-off Pre-flight

- Repo URL: founder confirms via `git remote -v` (current dev: local-only `feat/sprint-q12-deep-quality` branch)
- Activation key: minted by founder via Step 3 above
- Provider keys: 6 mandatory (Anthropic, Groq, Gemini, Cerebras, Cohere, Cloudflare) + optional (OpenRouter, vLLM)
- Setup instructions: `docs/setup/quickstart.md` (review per R94)
- Troubleshooting guide: `docs/qa/troubleshooting.md` (Caveat #12 Cerbos fix + Lighthouse `abs.local→localhost` reflected)
- Founder action items list: `docs/qa/founder_action_items.md` (per R93)

## 7. Live-Path-Verified Ledger (Sprint Q12 contributions)

| Round | live_path_verified | Notes |
|-------|--------------------|-------|
| R76 helm | source-only | dry-run PASS, production apply gated |
| R77 DR drill | spec only | gated by `ABS_DR_DRILL=1` env |
| R78 first-customer E2E | TRUE | TestClient is the live tester path |
| R82 Lighthouse fix | TRUE post-cron | `abs.local→localhost` shipped, first cron 2026-05-09 |
| R84 pricing | N/A | defaults to 0; live verifies on operator env set |
| R85 provider degradation | false | TestClient only; needs staging rotation |
| R86 license lifecycle | partial | JWT in-process; warn log surfaces in real journal |
| R87 magic-link | false | no real SMTP path tested |
| R89 Cerbos live deploy | spec only | founder runs deploy + verify |
| R90 Lighthouse artifact review | spec only | first cron 2026-05-09 |
| R91 final acceptance combined | TRUE (TestClient) | 6 phases all green; live cluster verify owed by founder |

## 8. Sign-off

Threshold sealed at HEAD `dbaeca8` on **2026-05-05** (S12 close-out). Tester may begin once the seven Founder Action Items above are completed AND the canonical full-suite command in §Status returns `0 failed / 0 errors`. The seven items are pre-deployment one-shots; once executed and signed off, this checklist becomes the entry document for the tester. Any subsequent backend code change must trigger an image rebuild, a full-suite re-run (canonical command), and a fresh R91 final acceptance E2E before re-handing off.

> **Mandatory pre-handoff verification (S12 lesson):** before tagging
> `handoff/v1`, founder runs the canonical full-suite command on the host
> shell and pastes the last line into this section. Selective-subset
> evidence is NOT acceptable for the seal — that path is what produced the
> false S11 GREEN. The single source of truth is the canonical command's
> last line.
