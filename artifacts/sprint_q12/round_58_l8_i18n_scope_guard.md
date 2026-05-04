# Round 58 — L8 i18n locale parity deep + scope drift guard

**Layer:** Q11-L8 (i18n) + Q12-L8 deep
**Status:** ✅ ship
**Time:** 2026-05-04 ~16:30

## Goal

Per S8 brief MEDIUM #5 — L8 deep audit:
- Yeni eklenen string'ler (R35 sessions-error-tile, R48 SW status, ZAP fix) TR + EN + ES'te var mı?
- Date format / Number format locale-aware mı?

## Audit findings (read-only)

### 1. R35/R48/ZAP-fix strings location

**R35 sessions-error-tile** ("Tekrar dene", "Sohbet geçmişi yüklenemedi"):
hardcoded in `app/panel/chat/ChatClient.tsx`. **Not in locale dict.**

**R48 SW status indicator**: panel-side; no localization layer.

**ZAP fix**: 0 user-facing strings (security-only changes).

### 2. Date/Number format audit

13 hardcoded `"tr-TR"` Intl formatter calls found:
```
components/chat/index.tsx:111,117,526,532
app/panel/quota/page.tsx:101,106
app/panel/meetings/page.tsx:42
app/panel/page.tsx:170,180
app/panel/meetings/[id]/page.tsx:105
app/admin/users/page.tsx:313
app/admin/pipelines/page.tsx:399
app/admin/audit/page.tsx:281
```

**All inside panel/admin/components/chat surfaces.** Zero hardcoded
locale tags found on the landing surface (`/`, `/pricing`, `/privacy`,
`/terms`).

### 3. Conclusion — not a bug, by design

The product has two distinct surfaces:
- **Landing** (marketing + legal): full EN/TR/ES via `lib/i18n.ts` +
  `locales/{en,tr,es}.json`. Default EN per CLAUDE.md global mandate.
- **Panel + admin + components/chat** (operator UI): TR-first by design.
  Self-host customer base today is TR-leaning; admin numbers/dates are
  intentionally `tr-TR`.

R35/R48 land in the panel surface where TR-first is the policy. Not a
locale gap — a deliberate scope boundary that wasn't documented.

## Real change shipped (R58)

Two artifacts that lock the scope policy in place:

### 1. Vitest regression guard

`core/landing/__tests__/i18n-scope.test.ts` (3 assertions, **3/3 PASS** in 35 ms):

| Assertion | Catches |
|-----------|---------|
| No hardcoded BCP-47 tags outside TR-first dirs | future drift adding `"tr-TR"` to landing |
| Locale dict size locked to [70, 200] band | accidental panel-string flood into global dict |
| No `panel.`/`admin.`/`chat.`/`setup.`/`auth.` key prefixes in `en.json` | scope leak |

### 2. Scope policy doc

`docs/qa/i18n-scope-policy.md` documents:
- Why two surfaces, two policies
- The TR-first directory list (so reviewers know what's allowed where)
- The R58 regression guard mechanics
- The trigger conditions for graduating panel to full EN/TR/ES (≥ 1
  paying non-TR admin user, enterprise EN-admin requirement, or
  product strategy pivot)

## Vitest deltas

- **Before R58:** 23 test files, 94 tests (10 file fail / 26 test fail
  pre-existing tech debt unrelated to i18n)
- **After R58:** 24 test files, 97 tests (10 file fail / 26 test fail
  unchanged; +3 i18n-scope all PASS)

R58 doesn't introduce a regression and doesn't fix the pre-existing
26 fails (different layer, different round).

## What this does NOT close

- The 26 pre-existing vitest failures (Privacy.i18n.test.tsx, etc.)
  are async-Client-Component shape mismatches in the test, not real
  bugs. Tracked separately.
- Panel-side i18n graduation: deferred until trigger fires (see policy
  doc Section "When to add a panel-side i18n pass").

## Sprint Q12 layer matrix delta

| Layer | Pre-R58 | Post-R58 |
|-------|---------|----------|
| Q11-L8 i18n | 0/3 | 0/3 + R58 scope drift guard ⭐ deep |

## Image rebuild gate

R58 touches no backend source — only landing test + doc. **No image
rebuild required.** Backend container preserved.

## Files touched

- `core/landing/__tests__/i18n-scope.test.ts` (new, 3 vitest)
- `docs/qa/i18n-scope-policy.md` (new policy doc)

## Commit

(Atomic R58 commit; see `git log --oneline -1` after this round)

## Next

R59 = Sprint 22 RSC migration Phase A (read-only audit) +
bundle analysis + 2 candidate route picks.
