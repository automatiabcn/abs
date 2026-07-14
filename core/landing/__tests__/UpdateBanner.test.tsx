/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UpdateBanner from "@/components/panel/UpdateBanner";

function mockCheck(body: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/v1/update/check")) {
      return new Response(JSON.stringify(body), { status: 200 });
    }
    if (url.includes("/v1/update/apply") && init?.method === "POST") {
      return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
    }
    return new Response("no", { status: 404 });
  });
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("UpdateBanner", () => {
  it("says nothing when the server is on the latest version", async () => {
    vi.stubGlobal("fetch", mockCheck({ state: "current", current: "1.4.0" }));
    render(<UpdateBanner />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("says nothing when the registry could not be reached", async () => {
    // `unknown` is our own failure to look, not news about their install.
    vi.stubGlobal(
      "fetch",
      mockCheck({ state: "unknown", current: "1.4.0", error: "upstream_unavailable" }),
    );
    render(<UpdateBanner />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("names both versions when an update is available", async () => {
    vi.stubGlobal(
      "fetch",
      mockCheck({ state: "available", current: "1.4.0", latest: "1.5.0" }),
    );
    render(<UpdateBanner />);
    const banner = await screen.findByTestId("update-banner");
    expect(banner.textContent).toContain("1.5.0");
    expect(banner.textContent).toContain("1.4.0");
  });

  it("warns that a critical release contains breaking changes", async () => {
    vi.stubGlobal(
      "fetch",
      mockCheck({
        state: "critical",
        current: "1.4.0",
        latest: "1.5.0",
        critical: true,
        breaking: true,
      }),
    );
    render(<UpdateBanner />);
    const banner = await screen.findByTestId("update-banner");
    expect(banner.getAttribute("aria-label")).toBe("Critical update available");
    expect(banner.textContent).toContain("breaking changes");
  });

  it("asks for the pull, and admits the host still has to finish it", async () => {
    // /v1/update/apply only *requests* the pull. Telling the operator the
    // upgrade is done when a `docker compose up -d` is still owed is the one
    // thing this banner must not do.
    vi.stubGlobal(
      "fetch",
      mockCheck({ state: "available", current: "1.4.0", latest: "1.5.0" }),
    );
    render(<UpdateBanner />);
    await userEvent.click(await screen.findByTestId("update-banner-apply"));
    const done = await screen.findByTestId("update-banner-requested");
    expect(done.textContent).toContain("docker compose pull");
  });

  it("says so when the pull could not be requested", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/v1/update/check")) {
          return new Response(
            JSON.stringify({ state: "available", current: "1.4.0", latest: "1.5.0" }),
            { status: 200 },
          );
        }
        return new Response("nope", { status: 401 });
      }),
    );
    render(<UpdateBanner />);
    await userEvent.click(await screen.findByTestId("update-banner-apply"));
    expect((await screen.findByTestId("update-banner-error")).textContent).toContain(
      "sign in as an admin",
    );
  });

  it("stays dismissed for that version, and only that version", async () => {
    vi.stubGlobal(
      "fetch",
      mockCheck({ state: "available", current: "1.4.0", latest: "1.5.0" }),
    );
    const first = render(<UpdateBanner />);
    await userEvent.click(await screen.findByTestId("update-banner-dismiss"));
    expect(screen.queryByTestId("update-banner")).toBeNull();
    first.unmount();

    // Same version again: still dismissed.
    const again = render(<UpdateBanner />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("update-banner")).toBeNull();
    again.unmount();

    // A newer release is a new notice — the dismissal must not silence it.
    vi.stubGlobal(
      "fetch",
      mockCheck({ state: "available", current: "1.4.0", latest: "1.6.0" }),
    );
    render(<UpdateBanner />);
    expect((await screen.findByTestId("update-banner")).textContent).toContain("1.6.0");
  });
});
