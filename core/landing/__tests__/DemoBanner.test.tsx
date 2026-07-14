import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DemoBanner from "@/components/DemoBanner";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  window.sessionStorage.clear();
});

afterEach(() => {
  mockFetch.mockReset();
});

describe("DemoBanner", () => {
  it("renders nothing when /v1/demo-mode/status reports enabled=false", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ enabled: false, mock_providers: false, seed_version: "v1" }),
    });
    const { container } = render(<DemoBanner />);
    // Wait one microtask for fetch promise to resolve, then assert no banner.
    await waitFor(() => {
      expect(container.querySelector('[data-testid="demo-banner"]')).toBeNull();
    });
  });

  it("renders banner with seed version when demo mode is enabled", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ enabled: true, mock_providers: true, seed_version: "v1" }),
    });
    render(<DemoBanner />);
    const banner = await screen.findByTestId("demo-banner");
    expect(banner.textContent).toMatch(/Demo Mode/);
    expect(banner.textContent).toMatch(/seed v1/);
    expect(banner.textContent).toMatch(/mock providers/);
  });
});
