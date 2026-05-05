# Round 81 — L18 offline ↔ online transition stress (R48 draft race)

**Date:** 2026-05-05 (Q12 Session 9)
**Branch:** `feat/sprint-q12-deep-quality`
**Layer:** Q12-L18 sweep 4 (offline drafts deep round)
**Commits:** 1 atomic (this round)

## Goal

Brief asks for "offline send + 5 messages queued + online → all flush in
order". Investigation: there is **no outbox / send-queue mechanism** in the
codebase. Only R48's `chat-draft.ts` ships, and it persists the *current*
textarea contents under a single `current` key — not a queue of pending
sends.

Building an outbox is a source-code change (new lib, new IndexedDB store,
new ChatClient hook, new SW message-replay logic) — that's a Sprint 22
follow-on, not a "deep round 6 test" round.

## What R81 ships instead

The **honest** offline↔online race the existing system can lose to: a
flapping connection while the user is typing must not lose, duplicate, or
corrupt the draft. R48's `saveDraft` runs from a `useEffect` on every
input change, so a flapping connection means many IndexedDB writes
interleaved with `online` / `offline` events.

`q12-l18-offline-online-stress.spec.ts` ships **3 tests**:

| Test | Race scenario |
|------|---------------|
| `draft survives 5-toggle O→F→O→F→O cycle without loss` | 5 offline/online toggles (each with 150 ms settle) while a draft is in the textarea; assert IDB still holds the draft + reload restores it |
| `five sequential offline edits all land in IndexedDB (no edit dropped)` | 5 incremental fills while offline; assert the last write wins (R48's single-`current`-key upsert contract under offline conditions) |
| `transitioning online does not wipe or duplicate the offline draft` | type while offline, flip online, assert neither React state nor IndexedDB has been touched (catches an `online`-handler regression that would retroactively wipe local state) |

Each test reads IndexedDB **directly** (bypassing the textarea) so the
assertion is on the persistence layer, not on React state. That's the
difference between "the textarea looks right" and "the contract for
cold-mount restore actually held under network flapping".

## Test results

```
3 [chromium-desktop] › q12-l18-offline-online-stress.spec.ts:140 › five sequential offline edits all land in IndexedDB (17.3s)
2 [chromium-desktop] › q12-l18-offline-online-stress.spec.ts:182 › transitioning online does not wipe or duplicate the offline draft (17.4s)
1 [chromium-desktop] › q12-l18-offline-online-stress.spec.ts:95  › draft survives 5-toggle O→F→O→F→O cycle without loss (18.1s)
3 passed (19.3s)
```

Playwright delta: +3 chromium-desktop tests. Cross-browser run (firefox /
webkit) deferred — the existing R63 `serviceWorkers: "block"` pattern is
in the related drafts spec, but this stress test does not need to block
SWs (it asserts on IDB, not on `page.route()`).

## Image rebuild gate

Frontend-only spec; backend code unchanged. Container exec gate not
triggered.

## Followups (not this round)

- **Outbox / send-queue mechanism**: build a separate IDB store
  `abs-chat-outbox` that the chat completion hook drains FIFO when
  `navigator.onLine` flips true. Once it exists, the brief's literal
  5-message-queue test becomes implementable. Sprint 22 scope.
- **Cross-browser propagation**: re-run this spec under firefox-desktop
  + webkit-desktop once the outbox lands; until then, the chromium-only
  coverage is sufficient since the same IDB/`useEffect` paths run
  identically across the engines we test.
