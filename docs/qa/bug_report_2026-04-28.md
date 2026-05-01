# Sprint 17 — QA Bug Report (2026-04-28)

End-to-end Playwright + axe-core sweep across the ABS landing site.

## Summary

| Suite | Tests | Pass | Fail (initial) | Fail (after fix) |
|---|---|---|---|---|
| Routes (status + console) | 9 | 9 | 0 | 0 |
| a11y (axe-core, WCAG 2.x A/AA) | 8 | 8 | 1 (`/beta`) | 0 |
| Responsive (3 viewports × 2 routes) | 6 | 6 | 0 | 0 |
| **Total** | **23** | **23** | **1** | **0** |

All blocking bugs were fixed during this sprint. Suite is green on `chromium-desktop`.

## Findings

### BUG-Q4-01 — `/beta` form fields fail WCAG 2 AA color-contrast (FIXED)

- **Severity:** P1 (serious — blocks WCAG 2 AA)
- **Surface:** `/beta` (BetaRequestForm.tsx)
- **Detection:** axe-core, rule `color-contrast`
- **Symptom:** five form controls (`#beta-email`, `#beta-name`, `#beta-company`, `#beta-use-case`, `#beta-lang`) reported a 1.04 contrast ratio (foreground `#f8fafc` on background `#ffffff`, expected ≥ 4.5:1). The cascade resolved typed text to near-white, making it invisible against the white card background.
- **Root cause:** every `<input>` / `<textarea>` / `<select>` shared `class="mt-1 w-full rounded-md border px-3 py-2"` without an explicit `text-*` color. The dark-mode body cascade pushed the inherited color to slate-50.
- **Fix:** added `bg-white text-slate-900 placeholder:text-slate-400` to all five fields in `core/landing/components/BetaRequestForm.tsx`. Re-run of `a11y.spec.ts /beta` → green.
- **Regression net:** the a11y suite now runs as part of `npm run test:e2e` and any future contrast regression on `/beta` (or any other public route) will fail CI.

## Suites

### `__tests__/playwright/routes.spec.ts`

8 public routes + 1 negative case. Each test asserts:

- `response.status() === 200` (404 for the negative case).
- `body.innerText.length > 20` (no blank render).
- No console errors aside from tolerated dev-mode warnings (Stripe, favicon, DevTools).

### `__tests__/playwright/a11y.spec.ts`

axe-core with `wcag2a / wcag2aa / wcag21a / wcag21aa` tags. Test fails on any violation with impact `critical` or `serious`. Lower-impact issues are logged for awareness but do not block.

### `__tests__/playwright/responsive.spec.ts`

3 breakpoints (mobile-360, tablet-768, desktop-1440) × 2 routes (`/`, `/pricing`). Each test:

- Navigates after `setViewportSize`.
- Asserts non-empty body.
- On mobile breakpoint, checks `documentElement.scrollWidth - clientWidth ≤ 2 px` (catches accidental horizontal scroll).

## Artifacts

- HTML report: `core/landing/playwright-report/index.html` (regenerated each run).
- Failure videos / traces: `core/landing/test-results/` (cleared between runs).
- The historical failure for BUG-Q4-01 is preserved at
  `core/landing/test-results/a11y-a11y-beta-chromium-desktop/error-context.md`.

## How to re-run locally

```bash
cd core/landing
npm run test:e2e            # headless, ~5 s
npm run test:e2e:headed     # headed mode (Sprint 17 brief asked for this)
```

The dev server is autobooted by `playwright.config.ts` on port 3457.
