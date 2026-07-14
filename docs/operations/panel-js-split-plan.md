# `panel.js` Modular Split Plan

**Status:** scheduled. The code is untouched because the panel has no automated regression net and a runtime regression would block the customer-facing dashboard.

## Why split

`core/backend/app/static/panel/assets/panel.js` is 788 lines of a single IIFE that mixes:

- 4 SSE event handlers (`onMetrics`, `onOrchestrator`, `onCohereUsage`, `onMcpTools`, `onBudget`).
- 8 widget renderers (each ~50-80 lines).
- 4 UI bindings (`bindLogout`, `bindTheme`, `bindAnchorNav`, `bindNotif`).
- DOM utilities (`safeParse`, `setText`, `clear`, `makeEl`).
- Notif buffer and toast queue.

A 788-line IIFE makes incremental changes risky and hard to test.

## Target shape

Convert to an ES-module bundle loaded via `<script type="module" src="...">`.

```
core/backend/app/static/panel/assets/
├── panel/
│   ├── main.js            ← entry; wires bindings + SSE.
│   ├── dom.js             ← safeParse / setText / clear / makeEl.
│   ├── sse.js             ← startSSE / reconnect logic / event router.
│   ├── widgets/
│   │   ├── metrics.js     ← onMetrics + spark renderer.
│   │   ├── orchestrator.js
│   │   ├── cohere.js
│   │   ├── mcp.js
│   │   └── budget.js
│   ├── ui/
│   │   ├── theme.js       ← bindTheme.
│   │   ├── nav.js         ← bindAnchorNav.
│   │   ├── auth.js        ← bindLogout.
│   │   └── notif.js       ← pushNotif + renderNotif + bindNotif.
│   └── util/
│       └── clock.js       ← startClock.
└── panel.js               ← thin shim that imports `./panel/main.js` for back-compat.
```

## HTML change

`core/backend/app/static/panel/index.html` line 384:

```diff
- <script src="/panel/assets/panel.js" defer></script>
+ <script type="module" src="/panel/assets/panel/main.js"></script>
```

The `panel.js` shim stays for any external bookmarks linking to it directly.

## Migration steps

1. Add a Playwright test under `core/landing/__tests__/playwright/panel.spec.ts` that:
   - Loads `/panel/`.
   - Asserts the 8 widget headings render.
   - Drives one SSE event via WebSocket / fetch mock and verifies the widget updates.
2. Capture pass/fail baseline.
3. Extract one module at a time, re-run the test, commit.
4. Remove the IIFE wrapper after the last extraction.

## Acceptance

- 0 regressions in the Playwright panel suite.
- No more files > 250 lines in `core/backend/app/static/panel/`.
- Theme switch + SSE reconnect + notif toast all functional.

## Why deferred

The split was listed as in-scope, but the panel has no automated coverage. Doing it blind risks breaking the dashboard for current customers. The plan above is the safe path; it should be executed together with the test scaffolding it depends on.
