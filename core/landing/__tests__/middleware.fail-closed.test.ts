// fail-CLOSED middleware behaviour.
// When the backend /auth/me check times out or throws, the request must
// redirect to /login?reason=backend-unreachable instead of falling through
// to the protected page.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { middleware } from "@/middleware";

type MockResponse = {
  type: "next" | "redirect";
  url?: string;
};

function buildRequest(path: string, cookieValue = "abs"): unknown {
  const url = new URL(`https://example.test${path}`);
  return {
    nextUrl: {
      pathname: path,
      clone: () => new URL(url.toString()),
    },
    cookies: {
      get: (name: string) =>
        name === "abs_session" ? { value: cookieValue } : undefined,
    },
  };
}

vi.mock("next/server", () => ({
  NextResponse: {
    next: (): MockResponse => ({ type: "next" }),
    redirect: (url: URL): MockResponse => ({
      type: "redirect",
      url: url.toString(),
    }),
  },
}));

describe("middleware fail-closed", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    globalThis.fetch = originalFetch;
  });

  it("redirects to /login when backend fetch throws (network unreachable)", async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValue(new Error("ECONNREFUSED")) as typeof fetch;

    const req = buildRequest("/panel/dashboard");
    const res = (await middleware(req as never)) as unknown as MockResponse;

    expect(res.type).toBe("redirect");
    expect(res.url).toContain("/login");
    expect(res.url).toContain("reason=backend-unreachable");
    expect(res.url).toContain("next=%2Fpanel%2Fdashboard");
  });

  it("redirects to /login when backend response is not ok (401)", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response("", { status: 401 })) as typeof fetch;

    const req = buildRequest("/admin/dashboard");
    const res = (await middleware(req as never)) as unknown as MockResponse;

    expect(res.type).toBe("redirect");
    expect(res.url).toContain("/login");
    expect(res.url).toContain("next=%2Fadmin%2Fdashboard");
  });
});
