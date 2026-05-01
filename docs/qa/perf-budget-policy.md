# Perf Budget Policy

## Budgets

| Budget | Target | Threshold (CI fail) | Tool |
|---|---|---|---|
| Lighthouse Performance | ≥ 95 | drop > 2 from main | lighthouse-ci |
| Lighthouse Accessibility | ≥ 95 | drop > 2 | lighthouse-ci |
| Lighthouse Best Practices | ≥ 95 | drop > 2 | lighthouse-ci |
| Lighthouse SEO | ≥ 95 | drop > 2 | lighthouse-ci |
| LCP | < 2.5 s | > 2.8 s | web-vitals + lighthouse |
| FID / INP | < 100 ms / < 200 ms | > 250 ms | web-vitals |
| CLS | < 0.1 | > 0.15 | web-vitals |
| First Load JS shared | < 100 kB | > 110 kB | bundlewatch |
| Per-route first-load JS | < 150 kB | > 175 kB | bundlewatch |
| Server response (TTFB) | < 600 ms | > 900 ms | lighthouse |

> The shared bundle currently sits at **102 kB** — the React 19 + Next 15 framework baseline (see `docs/qa/bundle-reports/2026-04-29-summary.md`). Until a Preact shim lands, the practical budget is "no regression beyond 102 kB."

## CI gates

`.github/workflows/perf-budget.yml` runs on every PR and on push to `main`. Three independent jobs:

1. **`lighthouse`** — `treosh/lighthouse-ci-action@v12` against a fresh `npm run build && npm run start` on `localhost:3000`. Routes audited: `/`, `/pricing`, `/showcase`, `/onboarding`. Assertions in `lighthouserc.json`.
2. **`bundlewatch`** — runs `bundlewatch` against `core/landing/bundlewatch.config.json` after `ANALYZE=false npm run build`.
3. **`web-vitals`** — Playwright `__tests__/playwright/web-vitals.spec.ts` collects LCP / CLS / INP via Chrome DevTools `Performance.metrics()` and asserts the budgets above.

### Failure modes

| Job | Trigger | Result |
|---|---|---|
| lighthouse | any score drops > 2 from main baseline | PR check fails with route + metric |
| bundlewatch | any chunk exceeds its budget OR shared > 110 kB | PR check fails with per-chunk diff |
| web-vitals | LCP > 2.8 s OR INP > 250 ms OR CLS > 0.15 | Playwright failure lists offending metric |

## Tooling

- **`next/font/google`** — Geist Variable + JetBrains Mono self-hosted, no runtime fetch, `display=swap`. Wired via `app/layout.tsx`, CSS variables consumed in `app/tokens.css`.
- **`next/image`** — Next 15 ships AVIF + WebP automatic format negotiation. Any image > 4 kB must use `<Image>`.
- **React 19 Suspense streaming SSR** — `app/` router default; each route ships a `loading.tsx` skeleton.
- **Bundle reports** — archived under `docs/qa/bundle-reports/` (treemap HTML + summary md per snapshot).

## How to read a Lighthouse CI failure

1. Open the failed `lighthouse` job in the PR checks list.
2. Download the artifact `lighthouse-ci-results.json`.
3. Find the route (`url`) and metric that breached.
4. **Intentional regression** (e.g. shipping a hero carousel that adds 3 pts to Performance):
   - Update `lighthouserc.json` in the same PR with the new target + commit message justifying it.
5. **Unintentional regression**:
   - Run `npm run lighthouse:local` (wraps `lhci collect` against the dev build).
   - Profile in Chrome DevTools Performance panel, fix the heaviest offender, re-run.

## How to read a bundlewatch failure

1. Open the workflow log for the `bundlewatch` job; per-chunk diff shows `+X kB` / `-Y kB`.
2. Map the chunk to a module: `npm run analyze` locally → open `.next/analyze/client.html`, search by chunk hash.
3. **Unintentional**: lazy-load via `next/dynamic`, or move third-party deps to a vendor chunk.
4. **Intentional**: edit `bundlewatch.config.json` budget + add a one-line justification.

## Local dev cycle

```bash
cd core/landing
npm run lighthouse:local   # builds + runs LHCI against localhost
npm run analyze            # ANALYZE=true npm run build → .next/analyze/client.html
npx playwright test web-vitals.spec.ts
```

Runs the same three checks the CI does, so you catch regressions before the PR.

## Sprint review cadence

Each sprint, the platform owner reviews:

1. **Lighthouse CI trend** — last 4 weeks of runs from the LHCI dashboard. Verify scores stay within the 2-point tolerance.
2. **Bundlewatch trend graph** — shared bundle + every high-traffic route.
3. **Production Web Vitals** — 75-percentile values from `/v1/internal/web-vitals`.

| 75-percentile vs. budget | Action |
|---|---|
| ≤ 80 % | no action |
| 80 % – 95 % | sprint backlog perf task assigned to owning team |
| > 95 % | P1 hot-fix |

Decisions logged in the sprint retro notes; any budget update must be committed to this file with a sprint-ticket reference in the commit message.
