/**
 * Fail-closed AdminLayout SSR probe.
 *
 * AdminLayout (RSC) backend /healthz probe fail edince redirect('/login?
 * calls reason=backend-unreachable') . Even if middleware is bypassed
 * defense-in-depth is active.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

// next/navigation.redirect throws — Next.js default behavior.
const redirectMock = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT: ${url}`);
});

vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirectMock(url),
}));

// AppShell/CommandPalette/QueryProvider/ThemeProvider — RSC tree
// stubs for it. This test only verifies probe + redirect behavior.
vi.mock("@/components/panel/CommandPaletteLazy", () => ({ default: () => null }));
vi.mock("@/components/shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/panel/PanelThemeProvider", () => ({
  PanelThemeProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/panel/ServiceWorkerRegister", () => ({ default: () => null }));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@/lib/query-client", () => ({
  QueryProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const originalFetch = global.fetch;

async function loadAdminLayout() {
  const mod = await import("@/app/admin/layout");
  return mod.default;
}

async function loadPanelLayout() {
  const mod = await import("@/app/panel/layout");
  return mod.default;
}

describe("AdminLayout — SSR fail-closed probe", () => {
  beforeEach(() => {
    redirectMock.mockClear();
    vi.resetModules();
  });
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("redirects to /login when backend /healthz returns non-OK", async () => {
    global.fetch = vi.fn(async () =>
      new Response("", { status: 503 }),
    ) as unknown as typeof fetch;
    const Layout = await loadAdminLayout();
    await expect(
      Layout({ children: null }),
    ).rejects.toThrow(/NEXT_REDIRECT.*backend-unreachable/);
    expect(redirectMock).toHaveBeenCalledWith("/login?reason=backend-unreachable");
  });

  it("redirects to /login when backend fetch throws (network error)", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const Layout = await loadAdminLayout();
    await expect(
      Layout({ children: null }),
    ).rejects.toThrow(/NEXT_REDIRECT.*backend-unreachable/);
    expect(redirectMock).toHaveBeenCalledWith("/login?reason=backend-unreachable");
  });

  it("renders the panel when backend /healthz is OK", async () => {
    global.fetch = vi.fn(async () =>
      new Response('{"ok":true}', { status: 200 }),
    ) as unknown as typeof fetch;
    const Layout = await loadAdminLayout();
    const node = await Layout({ children: null });
    expect(node).toBeDefined();
    expect(redirectMock).not.toHaveBeenCalled();
  });
});

describe("PanelLayout — SSR fail-closed probe", () => {
  beforeEach(() => {
    redirectMock.mockClear();
    vi.resetModules();
  });
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("redirects to /login when backend /healthz fails", async () => {
    global.fetch = vi.fn(async () =>
      new Response("", { status: 500 }),
    ) as unknown as typeof fetch;
    const Layout = await loadPanelLayout();
    await expect(
      Layout({ children: null }),
    ).rejects.toThrow(/NEXT_REDIRECT.*backend-unreachable/);
    expect(redirectMock).toHaveBeenCalledWith("/login?reason=backend-unreachable");
  });

  it("renders when backend /healthz is OK", async () => {
    global.fetch = vi.fn(async () =>
      new Response('{"ok":true}', { status: 200 }),
    ) as unknown as typeof fetch;
    const Layout = await loadPanelLayout();
    const node = await Layout({ children: null });
    expect(node).toBeDefined();
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
