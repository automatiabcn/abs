/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

/**
 * The admin gate, and the two-and-a-half seconds that used to open it.
 *
 * `_isAdmin()` ended in `} catch { return true; }`. A timeout, a 500, a dropped
 * connection — anything that was not a clean 401 or 403 — and a non-admin got the
 * whole console: users, audit log, providers, keys.
 *
 * The existing AdminLayoutFailClosed test could not catch it. It mocked `fetch`
 * with a single response for every URL, so `/healthz` and `/v1/admin/me` got the
 * same 200 and the denial branch was never rendered — the test asserted the door
 * was shut by only ever knocking as someone holding the key.
 *
 * These tests answer each URL separately, which is the only way to ask the
 * question at all.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT: ${url}`);
});
vi.mock("next/navigation", () => ({ redirect: (url: string) => redirectMock(url) }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ toString: () => "abs_session=x" }),
}));
vi.mock("@/components/panel/CommandPaletteLazy", () => ({ default: () => null }));
vi.mock("@/components/shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/panel/PanelThemeProvider", () => ({
  PanelThemeProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@/lib/query-client", () => ({
  QueryProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const originalFetch = global.fetch;

/** Healthy backend; the RBAC probe answers however the test says it does. */
function backend(rbac: () => Promise<Response>) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/healthz")) return new Response('{"ok":true}', { status: 200 });
    if (url.includes("/v1/admin/me")) return rbac();
    throw new Error(`unexpected fetch: ${url}`);
  }) as unknown as typeof fetch;
}

async function render() {
  const mod = await import("@/app/admin/layout");
  return (await mod.default({ children: "THE CONSOLE" })) as {
    props: Record<string, unknown>;
  };
}

/** Did the console itself render, or a notice? The children give it away. */
function renderedTheConsole(node: unknown): boolean {
  return JSON.stringify(node).includes("THE CONSOLE");
}

describe("the admin console does not open when it cannot check who you are", () => {
  beforeEach(() => {
    redirectMock.mockClear();
    vi.resetModules();
  });
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("opens for an admin", async () => {
    backend(async () => new Response('{"role":"admin"}', { status: 200 }));
    expect(renderedTheConsole(await render())).toBe(true);
  });

  it("stays shut for a signed-in non-admin", async () => {
    backend(async () => new Response("forbidden", { status: 403 }));
    const node = await render();
    expect(renderedTheConsole(node)).toBe(false);
    expect(JSON.stringify(node)).toContain("You need admin access");
  });

  it("stays shut when the RBAC check times out", async () => {
    // The exact failure the old code let through: not a refusal, just no answer.
    backend(async () => {
      throw new DOMException("The operation was aborted.", "TimeoutError");
    });
    const node = await render();
    expect(renderedTheConsole(node), "a timeout opened the admin console").toBe(false);
    expect(JSON.stringify(node)).toContain("could not check your access");
  });

  it("stays shut when the RBAC check errors", async () => {
    backend(async () => new Response("boom", { status: 500 }));
    const node = await render();
    expect(renderedTheConsole(node), "a 500 opened the admin console").toBe(false);
  });

  it("stays shut when the RBAC check answers with something unreadable", async () => {
    // A proxy in front of the backend returning its own 502 HTML page, say.
    backend(async () => new Response("<html>Bad Gateway</html>", { status: 502 }));
    expect(renderedTheConsole(await render()), "a 502 opened the admin console").toBe(false);
  });
});
