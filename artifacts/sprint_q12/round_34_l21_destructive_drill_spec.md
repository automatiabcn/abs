# Round 34 — L21 sweep 3 destructive drill spec (founder-gated)

**Sprint:** Q12 Session 5
**Layer:** L21 (fresh-deploy / safe drill) — sweep 3 (gated)
**Files touched:** 1 new shell script + 1 new test
**Status:** ✅ shipped — spec only (default-skip, founder runs locally)

---

## What this round ships

**`scripts/chaos/destructive_drill.sh`** — 7-step destructive
fresh-deploy drill, gated behind `ABS_DESTRUCTIVE_DRILL=1`. With the
gate off (default), the script prints a SKIP message explaining the
gate and exits 0. With the gate on, it runs against an isolated
docker compose namespace (default `q12-l21-drill` on port 28000) so
the live `infra-*` and `abs-cj-*` stacks (25-hour customer journey
state) remain untouched.

The 7 steps per iteration:
1. tear down namespace + volumes
2. clean SQLite scratch (drill-namespaced)
3. `docker compose build --no-cache backend` (full reproducibility)
4. bring stack up + wait up to 60s for healthz
5. `/healthz` → 200
6. `/readyz` → 200 (or graceful 503 with detail)
7. `/v1/marketplace/install` Content-Length 60 MB → 413 (live R27
   BodySizeLimit middleware proof)

The 7th step is the most informative: it proves the rebuilt
deployment carries the R27 fix to disk, into the image, into the
running container, AND into the live HTTP stack. A drill that boots
the stack but doesn't exercise the audit surface is just a healthz
check.

Knobs honoured (env vars):
- `ABS_DESTRUCTIVE_DRILL` (default 0 — SKIP)
- `ABS_DRILL_PROJECT` (default `q12-l21-drill`)
- `ABS_DRILL_PORT` (default 28000)
- `ABS_DRILL_ITERS` (default 1; brief asks for 3 — set to 3 for full)

---

## Safety guards shipped

1. **Default SKIP.** Without `ABS_DESTRUCTIVE_DRILL=1` the script
   exits 0 with a SKIP message — a CI that accidentally invokes the
   script does NOT delete volumes.
2. **Live-namespace refusal.** If `ABS_DRILL_PROJECT=infra` or
   `=abs-cj` (the live + customer journey namespaces), the script
   exits 3 with a refusal message *even with* the gate on. Belt and
   braces.
3. **Drill-namespaced data dir.** SQLite scratch deletion is scoped
   to `data/${PROJECT}/`, never `data/` root.
4. **Isolated compose project.** Default project name carries `q12-l21`
   prefix so docker volumes are namespaced and cannot collide with
   live infra volumes.

---

## Test inventory

`core/backend/tests/test_q12_l21_destructive_drill_spec.py` — 7 tests
that pin the *spec* without ever invoking the destructive part:

| # | Test | What it pins |
|---|------|---------------|
| 1 | `drill_script_exists` | file present at canonical path |
| 2 | `drill_script_executable` | mode 0755 |
| 3 | `drill_default_skip_message` | running with no env vars exits 0 + prints GATED |
| 4 | `drill_explicit_zero_also_skips` | ABS_DESTRUCTIVE_DRILL=0 → SKIP (any non-1 = off) |
| 5 | `drill_refuses_live_namespace` | gate on + `ABS_DRILL_PROJECT=infra` → exit 3 |
| 6 | `drill_explicitly_refuses_abs_cj_namespace` | same for `abs-cj` (customer journey) |
| 7 | `drill_documents_iters_default` | ABS_DRILL_ITERS env knob present + R27 audit proof (60000000 + 413 strings) baked in |

Each test runs in <1 s. None of them invokes the destructive path —
they exercise only the SKIP and refusal codepaths.

---

## Verification

```
host venv: 7/7 PASS in 0.44s
default invocation: prints GATED message + exits 0 ✓
ABS_DESTRUCTIVE_DRILL=0: SKIP ✓
ABS_DRILL_PROJECT=infra + gate on: exit 3 (live-namespace refusal) ✓
ABS_DRILL_PROJECT=abs-cj + gate on: exit 3 ✓
```

The actual drill (`ABS_DESTRUCTIVE_DRILL=1`) was NOT run in this
round per Session 5 brief KESİN YASAK: "Destructive drill founder
approval YOK ise SHIP edilmesin (env flag default skip)". The
founder approves locally before each prod rollout cut.

---

## Image + container evidence

```
no backend source touched → image rebuild N/A (CLAUDE.md backend-only
                            trigger; spec round)
container_pytest_pass: 7/7 (host venv; spec tests run subprocess
                       against the script — no container needed)
```

---

## L21 counter

| Sweep | Round | Vector | Verdict |
|-------|-------|--------|---------|
| 1 | R12 (S1) | alembic 0000–0008 chain + 6-step wizard E2E (3/3 PASS) | ✅ |
| 2 | R28 (S4) | 10× alembic roundtrip + JWT boundary + tamper matrix (11/11) | ✅ |
| 3 | **R34 (S5)** | **destructive drill spec + 7-step gate-tested skip path** | ✅ spec |

**Result: L21 → 3/3** (sweep 3 spec shipped; the live drill itself
remains a founder-run gate, not a sprint deliverable). The spec is
testable + maintainable + safe-by-default.

8 Q12 layers FULL CLEAN ⭐ unchanged. **L21 now also at 3/3** in spec
form (live execution still gated).

---

## Delegation evidence

Self-write — bash script + subprocess pytest is short and the
safety-gate semantics need exact knowledge of which env vars and
exit codes the existing chaos infrastructure uses (R5 / R10 / R32).

---

## Next

Session 5 closing summary + final pytest count.
