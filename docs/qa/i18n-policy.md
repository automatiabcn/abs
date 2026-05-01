# i18n Policy

## Supported locales

- **English (`en`)** — canonical source of truth. Every new key lands here first.
- **Turkish (`tr`)** — primary regional locale.
- **Spanish (`es`)** — secondary regional locale.

All three live at `core/landing/locales/<lang>.json` as flat string-to-string maps.

## Parity contract

The vitest suite at `core/landing/__tests__/locale-parity.test.ts` enforces:

1. EN, TR, ES all expose the **same set of keys** (no missing, no extra).
2. No string value is the empty string except a small allowlist of intentional placeholders (`pricing.*.note`).

Run locally with `npm run test`. The check is also part of the regular vitest suite that runs in CI on every PR.

## Adding a new key

1. Add it to `locales/en.json` with the canonical English copy.
2. Generate TR + ES translations. Preferred path is `mcp__abs__qual_translate` (round-trip verify) or `ask_kimi`/`ask_gptoss` with explicit length + technical-term constraints.
3. Add the same key to `locales/tr.json` and `locales/es.json` with the translated values.
4. Run `npm run test` — the parity guard fails fast if any of the three drifts.
5. If the new copy renders in a layout-sensitive surface (e.g. a card with a fixed width), eyeball the longest translation against the design.

## Technical terms

The following stay English in every locale:

- Product names: `RAG`, `Cerbos`, `Qdrant`, `OAuth 2.1`, `BGE-M3`, `MCP`, `Stripe`, `LangFuse`, `Recall.ai`, `ElevenLabs`.
- File formats: `PDF`, `Markdown`, `URL`.
- Brand: `ABS`, `Automatia`, `Self-Host`, `Maintenance`, `Managed Cloud`.

Translators: do **not** localise these — they're product-identifying tokens.

## RTL preparation

Although ABS does not currently ship an RTL locale (Arabic / Hebrew), every component must use **CSS logical properties** so a future RTL flip is one `dir="rtl"` away.

| Use | Don't use |
|---|---|
| `padding-inline`, `padding-block` | `padding-left`, `padding-right` |
| `margin-inline-start`, `margin-block-end` | `margin-left`, `margin-bottom` |
| `border-inline-end` | `border-right` |
| `inset-inline-start` | `left` |
| `text-align: start` | `text-align: left` |

Tailwind 3.4 ships logical-property utilities via `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`. Prefer those over `ml-*`, `pr-*`, `left-*`, `right-*`.

### Audit cadence

- Every Sprint 19+ component review checks new components for physical-property misuse.
- A future T-R0X "RTL flip" task will run `dir="rtl"` regression visual tests against the existing surfaces.

## Copy-drift detection

Outside the parity guard, content drift (an EN string updated without TR/ES catching up) requires a soft signal. Recommend:

1. CI step running `mcp__abs__qual_translate` on a sample of changed keys; raise a PR comment if the round-trip back-translation diverges by > 30% Levenshtein distance.
2. Flag in the Sprint 19 backlog as "i18n drift sentry."

## Locale switch UX

The Header renders a `LangSwitcher` (cookie-based). The cookie name is `NEXT_LOCALE`. When unset, the server falls back to the `Accept-Language` header per `lib/i18n.ts:detectLangFromAcceptHeader`.
