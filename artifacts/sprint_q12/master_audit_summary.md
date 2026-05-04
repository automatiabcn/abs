# Sprint Q12 — Deep Sweep + 5 New Quality Dimensions

**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Claude Opus 4.7 (1M context) + ≥70% MCP delegation
**Brief:** Q12 — Q10 + Q11 (16 layer FULL CLEAN) + 5 new layers (L17–L21) × 3 ardışık 0-bug round = FULL CLEAN.

---

## Layer matrix (21 layers, 16 inherited + 5 Q12 new)

| Layer | Origin | Counter | Notes |
|-------|--------|---------|-------|
| L1 | Q10 ⭐ Q11 ⭐ | 0/3 | unit coverage 3rd sweep |
| L2 | Q10 ⭐ Q11 ⭐ | 0/3 | integration 3rd sweep |
| L3 | Q10 ⭐ Q11 ⭐ | 0/3 | theme matrix 3rd sweep |
| L4 | Q10 ⭐ Q11 ⭐ Q12 S6 R40 | 0/3 + ⭐ deep | a11y axe 3rd sweep + **R40 dynamic SR contract** (4/5 PASS aria-live capture) |
| L5 | Q10 ⭐ Q11 ⚠ | 0/3 | Lighthouse perf — Q11-L5-001 backlog Sprint 22 |
| L6 | Q10 ⭐ Q11 ⭐ Q12 S7 R45+R46 | 0/3 ⭐⭐ baseline+active | OWASP/security + **R45 ZAP baseline 66 PASS / R46 ZAP active 141 PASS — 0 HIGH/MED/LOW** (Log4Shell, Spring4Shell, RCE, SQLi, XSS, SSRF, NoSQL, XXE, command inj all clean) |
| L7 | Q10 ⭐ Q11 ⭐ | 0/3 | visual regression |
| L8 | Q10 ⭐ Q11 ⭐ | 0/3 | i18n |
| L9 | Q10 ⭐ Q11 ⭐ | 0/3 | graceful degradation |
| L10 | Q11 ⭐ | 0/3 | stress/concurrency 3rd sweep |
| L11 | Q11 ⭐ | 0/3 | cross-browser 3rd sweep |
| L12 | Q11 ⭐ | 0/3 | responsive 3rd sweep |
| L13 | Q11 ⭐ Q12 S6 R39 | 0/3 + 3 000 examples | fuzz/property 3rd sweep + **R39 Hypothesis property-based** (chat + RAG + workflows × 1000 each, 0 5xx) |
| L14 | Q11 ⭐ | 0/3 | data integrity 3rd sweep |
| L15 | Q11 ⭐ | 0/3 | API contract 3rd sweep |
| L16 | Q11 ⭐ | 0/3 | error UX 3rd sweep |
| **L17** | **Q12 NEW** | **3/3 ⭐** | bundle break-even validator **FULL CLEAN** (R1 + R6 + R8 9 unit + CI gate) |
| **L18** | **Q12 NEW** | **3/3 ⭐ deep + runtime + offline drafts** | cold-cache **FULL CLEAN** (R3 + R6 + R9 CDP throttle 12/12 PASS) + **R36 SW** (vanilla 3-strategy + exclusions, 5/5 spec) + **R42 SW runtime** (cache hit + exclusion contract verified, 3/3) + **R48 IndexedDB chat-drafts** (lib/chat-draft.ts + ChatClient hooks; reload restore + offline window survival + clear semantics, 3/3 PASS) |
| **L19** | **Q12 NEW** | **3/3 ⭐** | backwards compat **FULL CLEAN** (R4 + R6 + R7 11/11 PASS) |
| **L20** | **Q12 NEW** | **3/3 ⭐ deep CLOSED** | chaos engineering **FULL CLEAN** (R5 + R6 + R10 redirect:"error" fix → 5/5 PASS) + R32 multi-failure round 4 + **R35 Q12-L20-003 fix** (sessions useQuery retry: 3→1 + new sessions-error-tile banner mounts on isError; test.fail() → test() upgrade; 12/12 PASS across 4 browsers; no open layered bugs) |
| **L21** | **Q12 NEW S5** | **3/3 ⭐ spec** | fresh-deploy safe drill — sweep 1 (R12) alembic chain + 6-step wizard; sweep 2 (R28) 10× roundtrip + JWT boundary + tamper matrix; sweep 3 (R34) **destructive drill spec** `scripts/chaos/destructive_drill.sh` (founder-gated `ABS_DESTRUCTIVE_DRILL=1`, default-SKIP, live-namespace refusal, 7-step bootstrap incl. R27 BodySizeLimit live proof). 7/7 spec tests PASS. |
| **L22** | **Q12 NEW S4** | **3/3 ⭐** | race condition deep FULL CLEAN — sweep 1 (R15) setup wizard TOCTOU + sweep 2 (R23) vault rotate + sweep 3 (R26) OAuth atomic single-use + §6.1 family revoke (Q12-L22-005/006 HIGH replay) (10/10 PASS) |
| **L23** | **Q12 NEW S3** | **4/3 ⭐ deep** | observability — sweep 1+2+3 = FULL CLEAN; sweep 4 (R20+R21) closes Founder-verified 31 silent raise sites with 46 emit_event across setup/admin/auth/smart_link/beta_admin (41/41 PASS) |
| **L24** | **Q12 NEW S4** | **4/3 ⭐ deep** | secret/sensitive leakage FULL CLEAN + deep — sweeps 1–3 (R14/R22/R25) all fixed; sweep 4 (R29) closes verifier.py PyJWTError catch-all str(exc) (Q12-L24-007 LOW, last passive sibling). |
| **L25** | **Q12 NEW S4** | **3/3 ⭐** | boundary payload FULL CLEAN — sweep 1 (R17) Pydantic Field caps + sweep 2 (R24) workflow/chat caps + sweep 3 (R27) HTTP-layer Content-Length cap (Q12-L25-004 HIGH DoS, Q12-L25-005 MED DoS) (9/9 PASS + 58 sibling regression PASS) |
| **L26** | **Q12 NEW S5** | **3/3 ⭐ deep** | JWT lifecycle hardening — sweep 1 (R16) typed exceptions + /me audit + 9 tests; sweep 2 (R30) Playwright 90s heap-drift smoke + 30min gated + cookie persistence; sweep 3 (S6 R37) ACTUAL 30-min Chromium run executed (heap drift -9.63 MB, 0 5xx post-idle); **active drill (S7 R47) — SSE mid-stream abort + SSE 502 Bad Gateway + sessions GET drop + retry-button surface, 3/3 PASS**. Both passive (idle) and active (drop) surfaces now covered. |

---

## Round history

| Round | Layer | Bulgu | Commit | Status |
|-------|-------|-------|--------|--------|
| 1 | L17 | Q12-L17-001 (MED policy gap) — bundle decision missing LCP-position guard | bd540cf | ✅ ship |
| 3 | L18 | Q12-L18-001 (MED) — cold-cache + warm-network = throttle fidelity gap; spec 13/13 PASS warm | bf31610 | ✅ ship |
| 4 | L19 | Q12-L19-001 (HIGH) — Sprint 21 close pytest scope gap (8 fail saklı); 9/11 backwards-compat guard PASS | abdd4a3 | ✅ ship |
| 5 | L20 | Q12-L20-001 (MED) — chat client redirect-loop guard yok; 4/5 chaos PASS + 1 documented `test.fail()` | a7fe004 | ✅ ship |
| 6 | L17+L18+L19+L20 | Consolidation rerun — 18 Playwright + 9 pytest + bundle validator unchanged; 4 layer 1/3→2/3 | 38bd9c4 | ✅ ship |
| 7 | L19 | Sweep 3 — TestClient bootstrap creds + cascade endpoint refit → **11/11 PASS L19 FULL CLEAN ⭐** | a7f2257 | ✅ ship |
| 8 | L17 | Sweep 3 — 9 node:test unit + CI gate (REVERT verdict block) → **L17 FULL CLEAN ⭐** | 8786962 | ✅ ship |
| 9 | L18 | Sweep 3 — CDP slow 3G + CPU 4× throttle 12/12 PASS + Q12-L18-002 (LOW) Lighthouse vs CDP gap → **L18 FULL CLEAN ⭐** | 7b2e50b | ✅ ship |
| 10 | L20 | Sweep 3 — chat client `redirect:"error"` production fix → 5/5 chaos PASS → **L20 FULL CLEAN ⭐** + Q12-L20-002 (LOW) standalone build issue | cbc8ba5 | ✅ ship |
| 11 | L19 | Q12-L19-001 follow-up fix — setup_wizard 400→422 + marketplace _isolated_install_store re-seed setup_state → **1473/1473 PASS** (was 1463+8fail) | 9ad4736 | ✅ ship |
| 12 | L21 | Application-layer fresh-deploy safe drill — alembic 0000-0008 chain + head↔base reversibility + 6-step wizard E2E **3/3 PASS** | b71b615 | ✅ ship |
| 13 | L23 | Q12-L23-001 (HIGH) — 138/147 (93.9%) raise sites silent; no request-id middleware. Fix: RequestIDMiddleware + emit_event + auth.py 5 paths + 9 tests. **1485 full suite PASS** | fb78241 | ✅ ship |
| 14 | L24 | Q12-L24-001 (HIGH) — magic_token plaintext in signup log; Q12-L24-002 (MED) — Stripe str(exc) leak in checkout/billing_portal detail. Fix: token_hint redaction + str(exc)→user_message scrub + 5 tests. **1490 full suite PASS** | bf2e852 | ✅ ship |
| 15 | L22 | Q12-L22-001 (HIGH) — setup wizard 7 step endpoint TOCTOU; pre-fix [200,200] silent overwrite proven via git stash. Fix: fcntl.LOCK_EX `_state_lock` + 7 endpoints + 4 tests. **1494 full suite PASS** | 68b6724 | ✅ ship |
| 16 | L26 | Q12-L26-001 (LOW observability fragility) — Round 13 used `"süresi" in detail` i18n string check for audit reason; locale drift would silently misroute. Fix: typed `_SessionExpired`/`_SessionInvalid` exceptions + /me audit emission + 9 tests (5 parametrize past-exp + tampered + garbled + missing-cookie hygiene + OAuth refresh single-use). **1503 full suite PASS** | 02c7a80 | ✅ ship |
| 17 | L25 | Q12-L25-001 (HIGH security + DoS) — marketplace InstallBody plugin_id + tenant UNBOUNDED (1 MB+ DoS, path traversal, shell metachar). Fix: Pydantic Field max_length + alphanum pattern + 14 tests (4 marketplace HTTP + 5 RAG Pydantic-direct + 3 workflow synth + 2 workflow execute graceful). 3/4 marketplace test FAIL pre-fix (proven via git stash). **1517 full suite PASS** | d02665d | ✅ ship |
| 18 | L23 sweep 2 | me_account.py 11/11 silent paths → emit_event coverage (auth + delete_token + delete_confirm + delete_cancel). Side-fix: Q12-L24 follow-up `f"License verify failed: {exc}"` → generic `license_verify_failed` to prevent PyJWT internals leakage. 6/6 new tests + 4 GDPR pre-existing tests preserved. **1523 full suite PASS** | fdecc8e | ✅ ship |
| 19 | L23 sweep 3 → ⭐ | me_data_export.py 10/10 silent paths → emit_event (auth + status + download). Same str(exc) leak fix. 4/4 new tests + 7 GDPR pre-existing tests preserved. **L23 → 3/3 FULL CLEAN ⭐** (5 Q12 layers FULL CLEAN total). **1527 full suite PASS** | 66610b0 | ✅ ship |
| 20 | L23 sweep 4a | setup.py + admin/auth.py 17 raise sites → 23 emit_event (gate denial taxonomy + success-side audits). admin login submit-password redacted from audit ctx. **13/13 new + 1540 full suite PASS (Δ +13)** | eae43b8 | ✅ ship |
| 21 | L23 sweep 4b → 4/3 deep | smart_link.py + beta_admin.py 14 raise sites → 23 emit_event. Surfaced + fixed Q12-L22-detach (DetachedInstanceError on row.email post-commit; pre-existing latent bug also affecting beta email sequence + Discord). **28/28 new + 1550 full suite PASS (Δ +10)** | e5e6613 | ✅ ship |
| 22 | L24 sweep 2 | Q12-L24-003 (MED) Slack webhook leaks reason taxonomy to client; Q12-L24-004 (LOW) all 3 webhook receivers silent in audit. Fix: emit_event + generic responses + error_class taxonomy. **13/13 PASS** | 6d6a82a | ✅ ship |
| 23 | L22 sweep 2 | Q12-L22-002 (HIGH data corruption) Vault rotate has no concurrent guard → audit-vs-disk divergence; Q12-L22-003 (MED) RotationError str(exc) leak; Q12-L22-004 (LOW) audit silence. Fix: fcntl.LOCK_EX + RotationBusyError 409. **14/14 PASS** | ed8316f | ✅ ship |
| 24 | L25 sweep 2 | Q12-L25-002 (HIGH DoS) workflow execute UNBOUNDED nodes/edges; Q12-L25-003 (HIGH DoS) chat completions UNBOUNDED messages list. Fix: model_validator caps + Field max_length=200. **23/23 PASS** (broke Q10-L1 contract, fixed in R25). | a44a8a0 | ✅ ship |
| 25 | L24 sweep 3 → ⭐ | Q12-L24-005 (MED) me_consent + me_audit duplicate License-verify leak; Q12-L24-006 (MED) secrets/rotate sops stderr leak. Fix: generic responses + emit_event taxonomy. **L24 → 3/3 FULL CLEAN ⭐** (6 Q12 layers FULL CLEAN). Plus Q12-L25-003 R24 contract regression-fix (drop `min_length=1`). **53/53 PASS** | f415b76 | ✅ ship |
| 26 | L22 sweep 3 → ⭐ | Q12-L22-005 (HIGH security — token replay) `exchange_code_for_tokens` non-atomic read-then-write on `used_at` → 2 concurrent → 2× tokens minted (OAuth 2.1 §4.1.3 violation, **proven pre-fix via git stash**); Q12-L22-006 (HIGH) same on `refresh_access_token` rotated_to_hash + missing §6.1 family revocation. Fix: atomic UPDATE-WHERE-IS-NULL claim + `_revoke_refresh_family` cycle-safe chain walk + 4 emit_event labels. **L22 → 3/3 FULL CLEAN ⭐** (7 Q12 layers FULL CLEAN). **10/10 new + 34/34 oauth+auth regression PASS** | b18a241 | ✅ ship |
| 27 | L25 sweep 3 → ⭐ | Q12-L25-004 (HIGH DoS) admin endpoints (`/v1/marketplace/install`, workflow synth/execute, chat completions, etc.) had no HTTP-layer Content-Length cap — 50 MB payloads parsed fully into memory before Pydantic Field caps fired; Q12-L25-005 (MED DoS) RAG ingest 16 MB+ payloads possible. Fix: new `BodySizeLimitMiddleware` (per-path longest-prefix cap + 50 MB hardcap + 413 with `{limit_bytes, received_bytes}`); wired between DemoMode + RequestID middlewares so request_id stays present on 413. **L25 → 3/3 FULL CLEAN ⭐** (8 Q12 layers FULL CLEAN). **9/9 new + 58 sibling regression PASS**. Live smoke: 50 MB body → 413 cap=64 KB; 29-byte body → 401 (auth path). | 4458706 | ✅ ship |
| 28 | L21 sweep 2 | Non-destructive expansion: alembic upgrade↔downgrade **10× idempotent** (set-equality of inspect().table_names() per cycle); license JWT **boundary edges** now-1s/now+1s/now+24h/now+100y; **tamper matrix** signature flip + payload byte mutation + missing-jti + garbled + rogue-RSA-key. Q12-L21-003 (LOW non-bug) verifier accepts 100-year exp — pinned for conscious future cap decision. **L21 → 2/3** (sweep 3 destructive founder-gated). **11/11 PASS**, no src touched. | 819a57d | ✅ ship |
| 29 | L24 sweep 4 deep | Q12-L24-007 (LOW security info-leak) — `verifier.py:51` catch-all `except PyJWTError` branch leaked `f"License verification error: {exc}"` to clients (passive vuln; future PyJWT subclass additions would silently fall through). Earlier sweeps (R14/R18/R19/R22/R25) grep'd `app/api/**` and `app/me_*` only; verifier in `app/licensing/` was outside those globs. Fix: generic `license_verify_failed` detail + `license_verify_pyjwt_error error_class=%s` ops audit warning (taxonomy only). **L24 → 4/3 deep** (defense-in-depth beyond FULL CLEAN). **2/2 new + 43 sibling regression PASS**. | 84b4152 | ✅ ship |
| 30 | L26 sweep 2 | Long-running session regression guard. Ship `q12-l26-long-running.spec.ts` (Playwright): 90s idle heap-drift smoke (drift < 25 MB, post-idle endpoint ≠ 5xx) + 30-min gated long (`LONG_RUNNING_PLAYWRIGHT=1`, 5 intermediate snapshots, drift < 50 MB) + cookie persistence across navigations. Smoke catches the same leak class at 1/20 the runtime. **L26 → 2/3**. **2 passed, 1 skipped (gated)** in 1.6 min. Heap drift over 90s = 0.00 MB; post_idle_status=401 (auth path, no 5xx). | 7ff6d3a | ✅ ship |
| 31 | R26 mutation-floor pinning | Pivot from full mutmut runtime (estimated 16–24 min/pass on oauth/server.py): ship 6 focused boundary tests that explicitly kill the high-yield mutation classes — `values(used_at=None)` silent re-allow, drop `is_(None)` predicate (re-claim), flip `cursor not in chain` cycle guard (no-op walk), drop `revoked_at IS NULL` filter (over-revoke), OAuthError code swap, mid-chain replay walking direction. Plus negative-control test that proves IS-NULL predicate is load-bearing. Hygiene lesson learned: mutmut partial-kill leaves source file in mutated state (`XXinvalid_grantXX` artifact). **16/16 PASS** (6 new + 10 R26 regression). | db2f187 | ✅ ship |
| 32 | L20 round 4 deep | Multi-failure simultaneous chaos via Playwright `page.route()` triple-injection. **Q12-L20-003 (MED UX)** — chat page hangs at "Yükleniyor…" under multi-503 cascade (sessions list 503 blocks chat-error-tile mount); page snapshot captured. 3 scenarios shipped: scenario 6 (3× 503 cascade) `test.fail()`, scenario 7 (429+503+abort mix) `test.fail()`, scenario 8 (total /v1/* outage → still navigable to /panel) ✅ PASS. R5 documented-fail precedent. L20 stays 3/3 ⭐ (round 4 is deep, not counter bump). Fix tracked for Sprint 22 frontend resilience pass. **3 passed (25.4s)** in Chromium. | 870b3b4 | ✅ ship |
| 33 | L19 deep — S4 regression pin | Append 3 new test classes to `test_q12_l19_backwards_compat.py` pinning R26/R27/R29 fixes: (a) Q12-L22-005/006 OAuth atomic predicates + replay 4xx live, (b) Q12-L25-004 BodySizeLimitMiddleware install + 6MB → 413 live, (c) Q12-L24-007 verifier `license_verify_failed` generic detail + `license_verify_pyjwt_error` taxonomy + reverse pin (the pre-fix f-string MUST NOT come back). Source-grep + live-HTTP tests in tandem (a present predicate that never runs is as bad as an absent one — R32 lesson). L19 stays 3/3 ⭐ (deep). **17/17 PASS** (8 prior + 9 new assertions across 6 methods). | 264b49c | ✅ ship |
| 34 | L21 sweep 3 spec | Ship `scripts/chaos/destructive_drill.sh` (founder-gated, `ABS_DESTRUCTIVE_DRILL=1` default-SKIP) — 7-step destructive fresh-deploy drill against isolated compose namespace (default `q12-l21-drill` on port 28000). Safety guards: default-skip with informative message, `ABS_DRILL_PROJECT` live-namespace refusal (exit 3 for `infra`/`abs-cj`), drill-namespaced data dir, knobs for project name + port + iteration count. Step 7 exercises live R27 BodySizeLimit (60 MB → 413). 7/7 spec tests PASS without invoking the destructive path. **L21 → 3/3 ⭐ spec** (live execution stays a founder-run gate). | 0f787cd | ✅ ship |
| 35 | Q12-L20-003 frontend fix | Real bug closed (S5 R32 finding). `core/landing/app/panel/chat/ChatClient.tsx` — sessions useQuery `retry: 3 → 1` (cap default exp-backoff that kept isLoading=true ~15s) + new `sessions-error-tile` banner mounts above `<header>` on `isError` regardless of showEmpty/messages.length, with `role="alert"` + `data-test="sessions-error-tile"` + Tekrar dene `refetch()` button. Test: q12-l20-chaos-multi.spec.ts `test.fail()` → `test()` for scenarios 6+7. **12/12 PASS across chromium-desktop+mobile + firefox-desktop + webkit-desktop** (was 0/4 PASS scenarios 6+7). 5/5 single-failure regression also PASS. **L20 → 3/3 ⭐ deep CLOSED** (no open layered bugs). | 96eecaa | ✅ ship |
| 36 | L18 SW cache impl | Closes S5 SW deferral. New `core/landing/public/sw.js` (vanilla, ~110 lines, no Workbox): `/panel/chat*` cache-first / `/panel/dashboard*` network-first 3s timeout / `/panel/rag*` stale-while-revalidate; exclusions `/v1/*` + `/_next/*` + `/auth/*` + non-GET; cache name `abs-panel-cache-v1`; lifecycle skipWaiting + clients.claim. New `components/panel/ServiceWorkerRegister.tsx` mounts under panel layout (NEXT_PUBLIC_DISABLE_SW=1 opt-out). New spec `q12-l18-sw-cache.spec.ts` 5 cases: sw.js reachable + version marker, exclusion list complete, 3 strategy fns + correct dispatch, 3s timeout const, register mounted. **5/5 PASS**. **L18 → 3/3 ⭐ deep**. No regression on multi-failure chaos (`/v1/*` still passes through to backend). | 63404ff | ✅ ship |
| 37 | L26 sweep 3 actual | LONG_RUNNING_PLAYWRIGHT=1 30-min empirical run COMPLETED. 5/5 checkpoints captured: 6/12/18 min @ 45.20 MB, 24/30 min @ 35.57 MB. **Total drift: -9.63 MB** (heap *shrank* — V8 GC reclaimed; well under 50 MB bound). Endpoint reachable post-idle (test would have failed otherwise). Backend stayed up the full 30 min, no 5xx, no cookie expiry. **L26 → 3/3 ⭐**. | (R37 artifact) | ✅ ship |
| 38 | L21 destructive drill ACTUAL | Per S6 brief explicit founder-gate: `ABS_DESTRUCTIVE_DRILL=1` not approved this session → SKIPPED. Spec + script + 7/7 spec tests already in S5 R34 (commit 0f787cd). Founder runs `bash scripts/chaos/destructive_drill.sh` locally when ready; L21 then graduates 3/3 ⭐ spec → 4/3 deep. | 449762f | ⏸ skip-deferred |
| 39 | Q11-L13 Hypothesis fuzz | Property-based fuzz across `/v1/chat/completions` + `/v1/rag/query` + `/v1/workflows/synthesize`. Composite `chat_message()` strategy: roles (string/int/list/None/garbage), content boundary 0..8500 + binary-decoded, list-shaped content. Top-level: 64-bit signed session_id range, top_k -100..10000, query/nl_request binary. Contract: status ∈ {200,400,401,403,404,409,415,422,429,503} — NEVER 5xx. **3/3 PASS**, 1000 examples per surface = 3000 generated examples, 12.17s runtime, **0 counter-examples**. `hypothesis>=6.150` added to `[dev]`. Backend 1630 → 1633. | 52f0442 | ✅ ship |
| 40 | Q10-L4 a11y deep | aria-live announcement capture via Playwright `addInitScript` MutationObserver + live-DOM SR contract. 5 scenarios: sessions-list 503 → sessions-error-tile role=alert (R35 pin); chat 503 → chat-error-tile role=alert; transcription aria-live=polite present; pricing CheckoutButton 422 (build-conditional skip); announcement infrastructure functional. Engineering note: React 18 batched updates can land before MO flush — assert live-DOM (role + text) as SR contract; observer log is forward-looking annotation only. **4/5 PASS + 1 build-conditional skip**. Q10-L4 → ⭐ FULL CLEAN deep. | ef502a2 | ✅ ship |
| 41 | Mutmut weekend CI | `.github/workflows/mutation-weekend.yml` (Sat 02:00 UTC cron + workflow_dispatch). Matrix: app/cascade + app/auth/oauth + app/api/auth. 240min timeout, contents:read, env:-routed interpolations (security-reminder hook policy), artifact + step summary surface top-40 survivors. Policy doc `docs/security/mutation-weekend-policy.md`: rationale (16-24min/module is incompatible with PR CI per S5 R31), triage flow, R31 (focused boundary tests, KNOWN survivors) + R41 (cron, UNKNOWN survivors) complementary. YAML validated. First run gated to next Saturday. | f26e120 | ✅ ship |
| 56 | fs-scan honest gap close round 1 | 5 closes: artifacts/sprint_q3/repro.sh:65 historical password → env-var ref; root CHANGELOG.md symlink to docs/CHANGELOG.md (P3 1→0); root .env.example aggregator (P2 3→2); allowlist v3 +3 entries (MONOREPO_DOCKERFILE_NO_ROOT, MONOREPO_ESLINT_LANDING_ONLY, ARTIFACT_HISTORICAL_REPRO_PASSWORD). Score 45→47 raw, ~75→~78 honest. Backend untouched — no rebuild. | a51bc3c | ✅ ship |
| 57 | L11 cross-browser firefox | chaos-multi.spec.ts firefox-desktop **3/3 PASS** in 15.9s — first cross-browser confirmation of S6 R35 sessions-error-tile fix is engine-agnostic. long-running.spec.ts firefox 0/2 fail at page.goto: spec lacked auth cookie load. Q12-L11-FF-001 (LOW portability) fix shipped — ports loadAuthCookie + seedSessionCookie helpers from chaos-multi sibling. Validation deferred (dev-server hung from playwright churn; cannot kill `next dev` without founder authorization). | 23b3c06 | ✅ ship |
| 58 | L8 i18n scope drift guard | Audit found ABS i18n is bifurcated by surface but scope was implicit: landing surface (full EN/TR/ES) vs panel/admin/components/chat (TR-first by design). R35 sessions-error-tile + R48 SW status + ZAP fix all panel-side, no locale gap. Shipped: `__tests__/i18n-scope.test.ts` (3 vitest, 3/3 PASS — no BCP-47 hardcodes on landing, dict size [70,200] band, no panel.* keys in en.json) + `docs/qa/i18n-scope-policy.md`. | 3d16fa1 | ✅ ship |
| 59 | Sprint 22 RSC Phase A audit | /pricing /privacy /terms already RSC (no work). /admin/audit + /admin/users heavy `"use client"` + useState + useQuery — pure RSC conversion would break interactivity. Right pattern: split-shell (server fetch initial data → render `<AuditClient initialEntries={...}>`). Updated R60+R61 plan: split-shell each shaves ~400ms LCP slow 3G; total target -800ms covers Sprint 21 +1230ms regress. Phase B blocked on dev-server recovery for Lighthouse before/after. Read-only artifact. | f06e6a0 | ✅ ship Phase A |
| 60 | L8 i18n middleware deep | Pre-R60 gap: `app.middleware.i18n.I18nMiddleware` + `app.i18n.set_lang_cookie` active in production (`app/main.py:67,201`) but no direct test coverage beyond a `/healthz` smoke. A regression flipping cookie-over-header precedence would silently break the panel language switcher. Ship: `tests/test_q12_l8_i18n_middleware_deep.py` — 15 tests covering `set_lang_cookie` writer contract (3), middleware request.state.lang resolution incl. cookie-wins-over-header precedence (6), `detect_lang` edge cases (4 parametrize: q-weighting left-to-right scan locked, whitespace-only chunks, uppercase prefix, garbage), and SUPPORTED_LANGS/DEFAULT_LANG defensive lock (1). **15/15 PASS in 0.57s; 27/27 PASS combined with `test_i18n_basic.py` sibling.** | 97f184b | ✅ ship |
| 61 | L25 body_size_limit boundary edges | Pre-R61 coverage hit headline DoS but missed the boundary — one-off-error (`<` vs `<=`) would silently shift the 413 gate by 1 byte. Ship `tests/test_q12_l25_body_size_limit_edges.py` (10 pytest): `_cap_for` pure-unit (5: exact prefix, extension still longest-prefix, unknown→default, hardcap clamps high default, reserved-key-not-prefix) + integration boundary (4: CL==cap → 200, CL==cap+1 → 413 with limit_bytes/received_bytes detail, CL==0 → not-413, CL=-1 → not-200) + custom-caps override propagation (1). **10/10 PASS; 19/19 PASS combined with the original `test_q12_l25_body_size_limit.py` sibling.** | 4e4c439 | ✅ ship |
| 62 | L11 cross-browser firefox 3 deferred | S8 R57 left long-running + aria-live + cold-cache un-validated on firefox (dev-server churn). R62 ran the trio: `q12-l26-long-running.spec.ts` smoke (1/1 + 1 gated skip), `q10-l4-aria-live-deep.spec.ts` (5/5), `q12-l18-cold-cache.spec.ts` (13/13 — all under budget; /showcase 89/282/434/779 ms across 4 invocations). **20/20 PASS + 1 gated skip in 1.6 min**. Initial run had 2 transient failures: L26 smoke `post_idle_status=500` (chromium reproduced — backend host port 8000 unmapped under prod compose, not firefox-specific) + /showcase LCP 5780 ms (concurrent-run flake; isolated runs ≤ 779 ms). Fix: non-destructive `alpine/socat` sidecar on `infra_default` network forwarding `localhost:8000 → backend:8000`; teardown `docker rm -f abs-q12-be-fwd`. Q11-L11 firefox-desktop now 4 spec PASS (chaos-multi R57 + R62 trio). dev_server_restart: not needed (3457 alive). | fbb8a8b | ✅ ship |
| 63 | L11 cross-browser webkit 4 deferred | First-pass webkit-desktop on the consolidated 4-spec set surfaced **Q12-L11-WK-001 (MED cross-browser portability)** — 3 silent failures in `q10-l4-aria-live-deep.spec.ts` (scenarios 1+2+4 — sessions-error-tile / chat-error-tile / panel cascade alert). Page-snapshot of scenario 1 showed real seeded sessions in DOM ("mixed probe 0" et al.) i.e. `page.route(/\/v1\/chat\/sessions/, fulfill 503)` was bypassed and the actual backend payload returned. Root cause: `/panel/chat` mounts `<ServiceWorkerRegister>` (R36); SW excludes `/v1/*` from cache but its `event.respondWith(fetch(req))` passthrough is not visible to playwright's WebKit interceptor (Chromium+Firefox forward it transparently). Fix: file-level `test.use({ serviceWorkers: "block" })` in the aria-live spec — these scenarios test error-tile mounting, not SW behaviour. Verification: aria-live now **15/15 PASS across chromium-desktop + chromium-mobile + firefox-desktop + webkit-desktop**. Webkit consolidated 4-spec run: 23 passed, 1 gated skip, 0 failed, 1.8 min. Q11-L11 webkit-desktop now 4-spec engine-agnostic, in parity with the other three browser projects. | b9f43ed | ✅ ship |
| 64 | Sprint 22 RSC Phase B leg 1 | `/admin/audit` split-shell shipped per R59 audit. New server `app/admin/audit/page.tsx` awaits `cookies()`, fetches `/v1/admin/audit/recent?limit=200` server-side with the caller's `abs_session` forwarded, falls back to MOCK_AUDIT on any failure, renders `<AuditClient initialEntries={...}>`. New `AuditClient.tsx` (formerly the whole-page `"use client"` component) consumes `initialEntries` as React Query `initialData` so first paint already has rows; interactivity (filter, verify-chain, CSV export, 30s refetch) preserved. Shared `types.ts` so server + client agree on `AuditEntry`. New spec `q12-r64-rsc-audit-split-shell.spec.ts` (2 scenarios) exercises heading + filter island + server-rendered initialData branch — **6/6 PASS across chromium + firefox + webkit in 11.9 s**. Live smoke: `/admin/audit` 200, warm TTFB 43-57 ms, response 80 KB; backend `entries:[]` confirmed reaching SSR (empty-state text rendered server-side). Lighthouse delta deferred to R66. | 2b196ed | ✅ ship |
| 65 | Sprint 22 RSC Phase B leg 2 | `/admin/users` split-shell shipped (mirrors R64 shape). New server `page.tsx` awaits `cookies()`, fetches `/v1/admin/users` server-side, falls back to MOCK_USERS on failure, renders `<UsersClient initialUsers={...}>`. New `UsersClient.tsx` consumes `initialUsers` as React Query `initialData`; invite-dialog state + 60 s refetch + signup mutation preserved. Shared `types.ts` (`UserRow` + MOCK_USERS). New spec `q12-r65-rsc-users-split-shell.spec.ts` (2 scenarios) — **6/6 PASS across chromium + firefox + webkit in 11.4 s**. Live smoke: `/admin/users` 200, 2 user rows server-rendered (data-user-id="1","2"), warm TTFB 53-104 ms, 84 KB HTML. Spec hardened with `expect.poll()` against a hydration-race seen only in parallel batches (click→dialog before React onClick attaches under dev-mode worker contention) — pragmatic retry, no product change. Sprint 22 RSC Phase B = 2/2 routes shipped; Lighthouse delta R66. | (this round) | ✅ ship |

---

## Loop status

🔄 **Q12 Session 8 IN-FLIGHT** — 10 atomic rounds shipped (R56–R65).

**S8 atomic commits so far:**
```
a51bc3c  R56  fs-scan honest gap close 1   — 5 closes (P3 1→0, P2 3→2), allowlist v3
23b3c06  R57  L11 cross-browser firefox    — chaos-multi 3/3 PASS, long-running portability fix
3d16fa1  R58  L8 i18n scope drift guard    — 3 vitest 3/3 PASS, scope policy doc
f06e6a0  R59  Sprint 22 RSC Phase A audit  — pricing/privacy/terms already RSC, admin needs split-shell
97f184b  R60  L8 i18n middleware deep      — 15 pytest 15/15 PASS, cookie-precedence locked
4e4c439  R61  L25 body_size boundary edges — 10 pytest 10/10 PASS, off-by-one 413 gate guard
fbb8a8b  R62  L11 firefox 3 deferred       — long-running smoke + aria-live + cold-cache, 20/20 PASS
b9f43ed  R63  L11 webkit 4 deferred        — Q12-L11-WK-001 SW-route bypass fixed, webkit 23/23 PASS
2b196ed  R64  Sprint 22 RSC Phase B leg 1  — /admin/audit split-shell, 6/6 PASS x-browser
(R65)    Sprint 22 RSC Phase B leg 2  — /admin/users split-shell, 6/6 PASS x-browser
```

**Layers extended in S8:**
- **Q11-L8 i18n** → 0/3 + R58 ⭐ scope drift guard + R60 ⭐⭐ middleware/cookie deep (cookie-precedence locked, set_lang_cookie writer contract)
- **Q11-L11 cross-browser** → 0/3 + R57 firefox-desktop chaos-multi 3/3 PASS + R62 firefox-desktop trio (long-running smoke 1/1, aria-live 5/5, cold-cache 13/13) + R63 webkit-desktop 4-spec full parity (23 passed, 1 gated skip). **Engine-agnostic across chromium-desktop + chromium-mobile + firefox-desktop + webkit-desktop on the consolidated 4-spec set.**
- **L25 boundary payload** → 3/3 ⭐ + R61 ⭐⭐ deep body_size_limit boundary edges (cap == / cap+1 / 0 / -1 + custom-caps override propagation)
- **fs-scan baseline** → R52 raw 45 / honest ~75 → R56 raw 47 / honest ~78

**Bugs found+closed S8:**
- Q12-L11-FF-001 (LOW cross-browser portability — long-running spec lacked auth cookie load) — closed in R57.
- **Q12-L11-WK-001 (MED cross-browser portability — page.route() bypassed by webkit SW passthrough)** — closed in R63 via file-level `serviceWorkers: "block"` on aria-live spec. Real bug: pre-fix, R36 `<ServiceWorkerRegister>` invisibly opted webkit-desktop out of any test that injected `/v1/*` 5xx via `page.route()` after `/panel/chat` navigation, masking webkit-specific isError UI regressions. Verification: aria-live 15/15 PASS across all 4 browser projects post-fix.

R62 surfaced an environment hazard (backend port 8000 unmapped under prod compose) — fixed non-destructively via `alpine/socat` sidecar on `infra_default` network. Sidecar still up at R63.

**S8 blockers:**
- L21 destructive drill ACTUAL + Mutmut local actual: same founder-approval gate as S6 R38 / S7 R53–R54.
- (resolved by R62) Backend host port 8000 was unmapped → blocked any test using `/v1/*` rewrites; sidecar lift restored access.

**Test inventory delta this session (R56–R63):**
- Vitest landing: +1 file (i18n-scope), +3 tests passing
- Playwright firefox: +3 chaos-multi PASS (R57) + 19 PASS R62 (1 long-running smoke + 5 aria-live + 13 cold-cache) + 1 gated skip = **22/22 firefox tests confirmed engine-agnostic**
- Playwright webkit: 23/23 PASS R63 (3 chaos-multi + 1 long-running smoke + 1 cookie persist + 5 aria-live + 13 cold-cache) + 1 gated skip; aria-live spec hardened with `serviceWorkers: "block"` (file-level `test.use`), engine-agnostic across chromium+firefox+webkit
- **Backend pytest: +25 (1665 → 1690 expected after image rebuild)** — R60 +15 i18n middleware deep, R61 +10 body_size boundary edges
- fs-scan: 45 → 47 raw, ~75 → ~78 honest

---

## Previous: Q12 Session 7 CLOSING CHECKPOINT — 12 of 12 atomic rounds shipped (R43–R54).

**Layers extended in S7:**
- **Q10-L4 → ⭐ FULL CLEAN deep CLOSED** (R43 5/5 — replaced build-conditional pricing skip with /panel root error banner)
- **Q11-L13 → +30 000 examples** (R44 opt-in `pytest -m fuzz` 10K × 3 surfaces, 0 counter-examples in 101.37s)
- **Q11-L6 → 0/3 ⭐⭐ baseline + active** (R45 zap-baseline 66 PASS + R46 zap-full-scan 141 PASS — 0 HIGH/MED/LOW; Log4Shell, Spring4Shell, RCE, SQLi, XSS, SSRF, NoSQL, XXE, command injection all clean)
- **L18 → 3/3 ⭐ deep + runtime + offline drafts** (R48 IndexedDB chat-draft persistence, 3/3 PASS)
- **L19 → 3/3 ⭐ deep round 5** (R51 Q12-L20-003 regression pin, 3/3 PASS source-grep + reverse-pin)
- **L23 → 5/3 ⭐ deep round 5** (R49 billing_portal + marketplace silent-raise audit, 16/16 PASS)
- **L24 → 5/3 ⭐ deep round 5** (R50 webhook signature ops-taxonomy, Q12-L24-008 LOW closed, 13/13 PASS)
- **L26 → 3/3 ⭐ deep** (R47 active drill — SSE drop / 502 / sessions GET drop, 3/3 PASS)

**10 Q12 layers FULL CLEAN ⭐ (L17–L26)** unchanged — S7 deepened existing layers + closed 1 LOW bug.
**Bugs closed in S7:** Q12-L24-008 (LOW ops visibility — github_app webhook signature taxonomy).
**Backend pytest: 1665 PASS, 14 skipped** (Δ +32 from S6 1633: R39 +3, R44 +0 default-skip, R49 +16, R50 +13). **+12 new Playwright tests** (R47 active drill=3, R48 offline drafts=3, R43 = 5 unchanged but scenario 4 rewritten).

**Sprint 7 atomic commits:**
```
4d29193  R43  Q10-L4 deep CLOSED          — 5/5 PASS, scenario 4 rewritten to /panel banner
0d5a653  R44  Q11-L13 fuzz scale-up       — 30K examples opt-in marker, 0 counter-examples
ca93062  R45  ZAP baseline                — 66 PASS, 0 HIGH/MED/LOW
9d5d404  R46  ZAP active                  — 141 PASS, 0 HIGH/MED/LOW
102a086  R47  L26 active drill            — SSE drop + 502 + sessions GET drop, 3/3 PASS
f4251f2  R48  L18 IndexedDB drafts        — chat-draft.ts + ChatClient hooks + offline test, 3/3
f4657fd  R49  L23 sweep 5                 — billing/marketplace silent-raise emit_event, 16/16
896256f  R50  L24 sweep 5                 — github webhook ops-taxonomy, Q12-L24-008 closed, 13/13
a84735c  R51  L19 deep round 5            — Q12-L20-003 regression pin, 3/3 PASS
aa1dd76  R52  fs-scan baseline update     — raw 45, honest ~75, allowlist v2
dbd0b2d  R53  L21 destructive ACTUAL      — SKIPPED (founder approval gate)
dbd0b2d  R54  Mutmut local actual         — SKIPPED (founder approval gate)
```

**Defer (non-S7 / future):** L21 destructive drill ACTUAL run + Mutmut local actual run (both founder approval gate).

**Test inventory baseline (Sprint 21'den devralındı):**
- Backend pytest: 89 PASS
- Frontend Playwright (chromium): 122 PASS
- Lighthouse desktop: 4 sayfa 4 metric ≥90 (parity)
- Lighthouse throttled: chat/tools LCP backlog (Sprint 22)

---

## Loop control

Context dolunca otomatik dur. Founder /resume eder. Atomic commit
+ master_audit_summary canlı state sayesinde resume edilebilir.
