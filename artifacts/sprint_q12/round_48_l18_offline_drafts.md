# Round 48 — L18 SW offline + IndexedDB chat drafts

**Sprint:** Q12 Session 7
**Layer:** L18 (cold-cache LCP / offline resilience) — IndexedDB
**Files touched:** 2 src + 1 new test
**Status:** ✅ shipped — 3/3 PASS chromium-desktop

---

## Brief

S6 R36 SW caches *responses*. R48 ships the matching *user-input*
persistence layer: chat textarea drafts persist across reload,
navigation, and offline windows.

## Design

### `core/landing/lib/chat-draft.ts` (NEW, ~85 lines)

Vanilla IndexedDB wrapper, no Workbox / idb dependencies. Two
exports:

```ts
loadDraft(): Promise<string>          // "" if no draft
saveDraft(text: string): Promise<void>  // "" deletes record
```

DB: `abs-chat-drafts`, store: `drafts`, key: `current` (single
record per browser profile). Bails silently on:
- SSR (no `window`)
- Browser without IndexedDB
- Quota / private-mode rejections

### `core/landing/app/panel/chat/ChatClient.tsx` (EDIT)

Two new useEffects:

```tsx
const draftHydratedRef = useRef(false);

useEffect(() => {
  // Cold-mount restore — only if input is empty (don't clobber
  // a fast typer who started before IndexedDB resolved).
  void loadDraft().then((draft) => {
    draftHydratedRef.current = true;
    if (draft && !input) setInput(draft);
  });
}, [setInput]);

useEffect(() => {
  if (!draftHydratedRef.current) return;
  void saveDraft(input);
}, [input]);
```

The `draftHydratedRef` gate prevents the save effect from firing
*before* the load effect resolves — otherwise saveDraft("") would
clobber the persisted record on initial render.

## File

### `core/landing/__tests__/playwright/q12-l18-offline-drafts.spec.ts` (NEW)

3 chromium-desktop tests, all using a `clearDraft(page)` helper
that wipes the IndexedDB before each scenario:

1. **Reload restore** — type → reload → assert textarea has draft
2. **Offline window** — `context.setOffline(true)` → type → read
   IndexedDB directly (no reload, since dev-server reload requires
   network) → assert stored == typed
3. **Clear semantics** — fill then empty → IndexedDB record
   deleted (queries return "deleted" sentinel)

## Verification

```
$ npx playwright test __tests__/playwright/q12-l18-offline-drafts.spec.ts \
    --workers=1 --project=chromium-desktop

  ✓ draft restores after a normal reload (3.8s)
  ✓ draft survives an offline window (1.8s)
  ✓ clearing the draft deletes the IndexedDB record (2.3s)

  3 passed (10.2s)
```

## Image rebuild

N/A — frontend-only round. Backend unchanged.

## Layer matrix delta

| Layer | Before R48 | After R48 |
|-------|------------|-----------|
| L18 | 3/3 ⭐ deep + runtime (R36 SW + R42 cache hit) | **3/3 ⭐ deep + runtime + offline drafts** (R36 + R42 + R48 IndexedDB persistence) |

L18 stays at 3/3 ⭐ counter — R48 adds depth on the offline
input-persistence axis.

## Counters

- Backend pytest: unchanged 1665.
- Playwright: **+3 new tests**.
- Atomic commits: 1.
