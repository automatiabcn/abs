/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What a brand-new customer sees the first time they ask the product a question
// with no provider key configured — which, on the free tier, is the default state
// of a server that has just finished the setup wizard.
//
// The backend answers 503 with a body it wrote for exactly this person:
//   {"detail": {"error": "all_providers_unavailable", "hint": "Add at least one
//    provider key under Settings → Providers.", ...}}
//
// The client only ever read `detail` when it was a *string*, so this object fell
// through to "Backend 503" — a status code, shown to someone who has never seen
// this product before, in place of the one sentence that would have unstuck them.

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useChat } from "@/lib/chat-stream";

function respondWith(status: number, body: unknown) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("what the chat says when it cannot answer", () => {
  it("shows the server's own hint, not the status code", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith(503, {
        detail: {
          error: "all_providers_unavailable",
          providers_tried: [],
          retry_after: 60,
          hint: "Add at least one provider key under Settings → Providers.",
        },
      }),
    );

    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send("Hello, what can you do?");
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.error).toContain("Add at least one provider key");
    expect(result.current.error).not.toContain("Backend 503");
  });

  it("still handles the string form of detail", async () => {
    vi.stubGlobal("fetch", respondWith(400, { detail: "message too long" }));

    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send("…");
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.error).toContain("message too long");
  });

  it("falls back to the status when the server explains nothing", async () => {
    vi.stubGlobal("fetch", respondWith(500, {}));

    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send("…");
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.error).toContain("500");
  });
});
