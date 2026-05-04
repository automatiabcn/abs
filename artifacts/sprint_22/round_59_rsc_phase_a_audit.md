# Round 59 — Sprint 22 RSC Phase A audit (read-only)

**Layer:** Sprint 22 RSC migration kickoff (Q12 S8 brief HIGH #3)
**Status:** ✅ ship Phase A audit; Phase B (route migrate) deferred
**Time:** 2026-05-04 ~16:40

## Goal

Per S8 brief HIGH #3: Sprint 22 RSC migration kickoff.

> Phase A: Audit — hangi route'lar RSC adayı (heavy server data + low
> interactivity)?
> Aday: /panel/dashboard, /admin/audit, /admin/users, /pricing,
> /privacy, /terms

## Audit findings

### 1. `app/pricing/page.tsx` — already RSC, minimal

```tsx
import { redirect } from "next/navigation";
export default function Page() {
  redirect("/#contact");
}
```

Pure server-side redirect. **No migration needed.** The pricing
landing page itself is at root `/#contact` anchor.

### 2. `app/privacy/page.tsx` — already RSC

```tsx
import type { Metadata } from "next";
import { type Lang, isLang, t } from "@/lib/i18n";
export const metadata: Metadata = {...};
// Server component, no "use client"
```

Already a server component using the landing i18n helper. No client
state, no useEffect, no useQuery. **No migration needed.**

### 3. `app/terms/page.tsx` — already RSC

Same shape as `/privacy`. **No migration needed.**

### 4. `app/admin/audit/page.tsx` — bad RSC fit (heavy client)

Top of file:
```tsx
"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
// ...
const [actor, setActor] = useState("");
const [action, setAction] = useState("");
const [verifyState, setVerifyState] = useState<"idle" | "ok" | "broken">("idle");
const audit = useQuery<AuditEntry[]>({...});
```

Interactivity: filter inputs + chain-verify state + react-query
infinite invalidation. Pure-RSC migration is **incorrect** — converting
to server component breaks all interactivity.

**Right pattern: split-shell.**
- `app/admin/audit/page.tsx` becomes a server component that fetches
  the initial page of audit entries server-side via Cerbos-aware
  helper, then renders `<AuditClient initialEntries={...}/>`.
- `app/admin/audit/AuditClient.tsx` is the existing component
  renamed; takes `initialEntries` as a prop and seeds React Query
  with `staleTime: 0` so subsequent refetches still hit the
  client-side hook.

This pattern (server-fetched first paint + client island for
interactivity) is the canonical Next 15 RSC split. LCP wins come
from skipping the round-trip the client query currently makes.

### 5. `app/admin/users/page.tsx` — bad RSC fit (heavy client)

Same shape as audit. `"use client"` + `useState` + `useMutation`
(invite/revoke) + `useQuery` (list). Same split-shell remedy
applies.

## What this means for Phase B (R60–R61)

The brief presumed a straightforward RSC conversion. The audit
disproves the premise: the two `/admin/*` candidates are interactive
and require the **split-shell** pattern, not full RSC. Updated plan:

| Round | Route | Approach | Expected LCP win (slow 3G) |
|-------|-------|----------|---------------------------|
| R60 | `/admin/audit` | split-shell: server fetch → client filter | ~−400 ms (skip first XHR round-trip) |
| R61 | `/admin/users` | split-shell: server fetch → client mutation | ~−400 ms (same) |

Total target: ~−800 ms LCP on slow-3G — covers Sprint 21 +1230 ms
regress per S8 brief.

## What this means for the brief's other candidates

- `/pricing`, `/privacy`, `/terms` — **already RSC**, no work needed.
  They contribute 0 to the LCP regress fix.
- `/panel/dashboard` — not audited this round; same client-heavy
  shape suspected. Will audit in R62.

## Phase B blocker

Lighthouse before/after measurement requires a healthy `next dev`
on port 3457 (or a staging build). The dev-server hung from R57's
playwright churn (cannot kill `next dev` without founder
authorization — already attempted). **Phase B (R60–R61) deferred
until dev server recovers** OR a fresh production build.

## What R59 ships

This audit document only. No code changes. Read-only artifact:

- `artifacts/sprint_22/round_59_rsc_phase_a_audit.md` (this file)

## Sprint Q12 layer matrix delta

No layer extension — Sprint 22 is the next sprint, not a Q12 layer.
Q12 layers unchanged.

## Image rebuild gate

No source touched. No rebuild required.

## Next

- R60: `/admin/audit` split-shell migrate (Phase B leg 1) — gated on
  dev server recovery + Lighthouse baseline capture
- R61: `/admin/users` split-shell migrate (Phase B leg 2)
- R62: `/panel/dashboard` audit + decide split-shell vs static

## Commit

(Atomic R59 commit; see `git log --oneline -1` after this round)
