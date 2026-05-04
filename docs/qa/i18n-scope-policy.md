# ABS Landing i18n — Scope Policy

**Status:** ratified Q12 Session 8 R58 (2026-05-04)
**Owner:** frontend
**Related:** `lib/i18n.ts`, `locales/{en,tr,es}.json`, `__tests__/locale-parity.test.ts`, `__tests__/i18n-scope.test.ts`

---

## Why this document exists

ABS internationalisation is **bifurcated** by surface. The two halves have
different scope, different default languages, and different drift risks.
Before Q12 R58 the split was implicit; new engineers occasionally
mis-routed a panel string into the global locale dict, or hardcoded
`tr-TR` Intl formatters on the landing surface. R58 ships a vitest
regression guard (`__tests__/i18n-scope.test.ts`) and this policy.

---

## Two surfaces, two policies

### 1. Landing surface (marketing + legal)

**Routes:** `/`, `/pricing`, `/privacy`, `/terms`, `/legal/*`, root layout
chrome (Header, Footer).

**Default lang:** `en`. Per CLAUDE.md *“ürün globale satılır → default
İngilizce”*. Marketing copy is shipped in EN first; TR + ES are
maintained for parity.

**Translation source of truth:** `core/landing/lib/i18n.ts` +
`locales/{en,tr,es}.json` (≈ 75 keys, locked to [70, 200] band by
R58 regression guard).

**Rules:**

- Every visible string passes through `t(key, lang)`.
- Locale-aware Intl formatters take the active `lang` as a parameter,
  never a literal `"tr-TR"`/`"en-US"`/etc.
- `parity` test (existing): every key in `en.json` exists in `tr.json`
  and `es.json`, no extras, no empty strings.
- `scope` test (R58): no panel/admin/chat key prefixes leak into the
  global dict.

### 2. Panel + admin + components/chat (operator UI)

**Routes:** `/panel/*`, `/admin/*`, `/setup/*`, `/auth/*`, `/login`,
`/signup`. Components: `components/chat/`, `components/panel/`,
`components/onboarding/`.

**Default lang:** Turkish first by design. The self-host operator UI
targets the early TR-leaning customer base; numbers + dates are
formatted with `toLocaleString("tr-TR")` and copy is hardcoded TR.

**Why TR-first here is OK:** the operator who runs ABS on their own
infra is choosing to deploy a TR-language admin surface. A DE-language
end customer hitting the **landing** surface still gets EN/TR/ES
selection — only the post-purchase admin panel is TR-first. This is a
deliberate, scope-bounded design choice.

**Rules:**

- TR literal strings + `tr-TR` Intl formatters are allowed inside the
  TR-first directories.
- Panel/admin keys must NOT enter the global locale dict — they live
  inline, where they belong scope-wise.
- If/when the operator UI ships an i18n pass, it will use a separate
  `locales/panel/{en,tr,es}.json` namespace; do not pollute the
  marketing dict pre-emptively.

---

## R58 regression guard test

`__tests__/i18n-scope.test.ts` ships three assertions:

1. **No hardcoded BCP-47 locale tags on landing surface.** Walks
   `app/` + `components/` excluding TR-first prefixes, greps for
   `"tr-TR"`/`"en-US"`/`"en-GB"`/`"es-ES"`/`"es-419"` literals, fails
   the build with the offending file list.

2. **Locale dict size locked.** Each of `{en,tr,es}.json` must hold
   between 70 and 200 keys. A jump outside that band is the canary
   for *“someone added the entire panel to the global dict”*.

3. **Locale dict scope is landing-only.** Bails if any key prefixed
   `panel.` / `admin.` / `chat.` / `setup.` / `auth.` ever lands in
   `en.json`.

Run locally:

```bash
cd core/landing
npx vitest run __tests__/i18n-scope.test.ts
# Expected: 3/3 PASS
```

---

## When to add a panel-side i18n pass

Tracked as Q12-L8-002 (no severity yet — design decision pending). The
trigger to graduate panel from TR-first to EN/TR/ES is:

- ≥ 1 paying non-TR customer requests EN/ES admin
- OR an enterprise contract makes EN admin a hard requirement
- OR product strategy decides TR-first is no longer the founder bet

When that trigger fires:

1. Create `core/landing/locales/panel/{en,tr,es}.json`.
2. Build a panel-scoped `t()` helper or extend `lib/i18n.ts` with a
   `namespace` parameter.
3. Migrate panel components surface-by-surface (chat → admin → setup).
4. Update R58 scope test to allow `panel.*` keys in the panel dict
   (still fail if they leak into the marketing dict).
5. Drop the `tr-TR` Intl literals; pass `lang` through.

Until that trigger fires, the policy above stays.

---

## Ratification log

| Date | Decision | Reference |
|------|----------|-----------|
| 2026-04-28 | T-061 ships PricingPage with EN/TR/ES at landing scope | session_resume_state_t061.md |
| 2026-04-28 | T-R06 locale-parity test added | __tests__/locale-parity.test.ts |
| 2026-04-29 | Sprint 19 onboarding flow stays TR-first inside operator UI | session_resume_state_s03_4.md |
| 2026-05-04 | Q12 R58 ratifies the bifurcation, adds scope drift guard | this doc |
