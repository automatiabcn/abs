# ABS Sprint Lessons (internal process notes)

These are operational lessons accrued across ABS sprints. Each entry is a process
rule the worker + founder honour by default; departures need an explicit
rationale in the sprint dispatch.

This file is **internal to the maintainer team**. It is checked in so future
worker sessions (and any contributor reviewing past behaviour) can find the
same constraints in the same place.

## Lesson 1 — No destructive cleanup without an explicit owner ask
Don't `rm -rf`, `git reset --hard`, force-push, or close PRs/issues that look
abandoned without an explicit go from the founder.

## Lesson 2 — No unauthorised new dependencies
Adding a package needs justification in the commit/PR body. Lockfile bumps from
Dependabot don't count.

## Lesson 3 — Don't touch `/Users/eneseserkan/Main/Automatia BCN/SERVER/`
That tree is the maintainer's orchestrator. The customer repo (this one) only
writes to `abs-server-product/`.

## Lesson 4 — Brand-neutral commits
Sibling projects (LeadPipe, InvoiceFlow, ShopOps, AdOps, AutoPilot Business)
are not referenced from ABS commit bodies or code comments.

## Lesson 5 — Don't modify `scripts/release.sh` without flagging
The release script is the only path that builds + pushes the customer-facing
images. Edits land in their own commit with an explicit rationale (see
Sprint 2G ITEM 1 for an example).

## Lesson 6 — One commit per ITEM
Sprint deliverables are commitable per ITEM. Avoid grouped commits unless two
ITEMs share a single root-cause (e.g. Sprint 2G ITEM 4 + ITEM 5).

## Lesson 7 — Verify before claiming "tested"
Run the actual test suite + paste the output in the result.md. "I'd expect
this to pass" is not evidence.

## Lesson 8 — Type checking + linters are CI gates, not suggestions
If `ruff`/`mypy`/`tsc`/`vitest` fails locally, fix before commit.

## Lesson 9 — Documented exceptions over silent skips
If a test is intentionally skipped, mark it with a comment + the reason. Same
for CodeQL/Bandit dismissals (Lesson 11).

## Lesson 10 — Carry-overs live in the next dispatch, not in a TODO comment
If an ITEM ships partial, the unfinished part is named explicitly in the next
sprint's brief — not left as a `# TODO Sprint NN` in code.

## Lesson 11 — Per-alert documented dismissal, no mass-dismiss
CodeQL / Bandit / Dependabot alerts are either fixed in code or dismissed
individually with a written rationale (worker writes the rationale; founder
clicks dismiss in the UI when the auto-mode classifier blocks the API call).

## Lesson 12 — No `Co-Authored-By` trailer
Every Sprint 2D+ commit ships without the trailer.

## Lesson 13 — Never echo secrets to the transcript
PAT / Stripe key / OAuth token reads use the
`GH_TOKEN=$(ssh ai-pc 'cat ~/keys/…')` inline pattern. Any tool that prints
the token (e.g. `gh auth status`) is piped through
`sed 's/Token: .*$/Token: [redacted]/g'` before display.

## Lesson 14 — Production deploys are single-actor + per-action approval
Tag pushes for any `v*` tag (rc or GA), Hetzner SSH deploys, and Stripe live-mode
toggles pause for an explicit founder go signal via `AskUserQuestion` or chat
confirmation. No background SSH sessions.

## Lesson 15 (revised, Sprint 2G ITEM 1) — Post-`release.sh` ship integrity verify (3-check)
A sprint may declare "shipped" only after **three consecutive GREEN checks**
on the release tag, run AFTER `release.sh` returns:

1. `git push origin <tag>` exit 0 (no stderr suppression, no `|| echo`).
2. `gh release view <tag>` returns 0 + `published_at` non-null.
3. `git ls-remote --tags origin | grep "refs/tags/<tag>$"` returns exactly
   one line.

If any of the three fails the sprint is **NOT shipped**; the worker's
result.md may not claim "shipped" until all three pass and the command
transcripts are pasted into the result.

**Why this exists:** Sprint 2D (rc9) + Sprint 2E (rc10) + Sprint 2F (rc11) all
skipped the tag-push verification — three sprints shipped images to GHCR
with no corresponding git tag on origin. The root-cause + reconciliation
plan live at `_agent-tasks/SHIP_INTEGRITY_AUDIT_2026-05-11.md`. The fix
(`scripts/release.sh` lines 127-150) removes the `2>/dev/null || echo`
masking and adds an explicit verification gate.

**Skipping this lesson also weakens Lesson 14:** Hetzner deploys keyed on
"the tag is on origin" silently run against an image that was only ever in
GHCR. The two lessons reinforce each other.

## Lesson 16 — Brand-neutral commits (carry of Lesson 4 with stricter wording)
No sibling-project name, no cross-project URL, no `Co-Authored-By` from the
sibling-project bot. Each commit reads as if ABS is the only project in the
world.

## Lesson 17 — Auto-mode classifier blocks need a chat-side confirmation
When the Claude Code auto-mode classifier blocks an action (e.g. CodeQL
dismissal, repo-admin PATCH), the worker:

1. Documents the intended action + rationale in the relevant
   `_agent-tasks/F*_*_READY.md` packet.
2. Asks the founder via `AskUserQuestion` to either approve the action or
   take it over via the UI.

The worker does not re-attempt the same call. (Source: Sprint 2G ITEM 9 #42
+ ITEM 14 repo About PATCH.)

---

## Footer

This file is updated whenever a new lesson is added or an existing one is
revised. The revision is called out in the sprint dispatch and the new
wording is pasted verbatim into this file.

Last revision: **2026-05-12** — Sprint 2G ITEM 1 added Lesson 15 revised
3-check wording + Lesson 17.
