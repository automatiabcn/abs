import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import Demo from "@/components/Demo";

describe("Demo (018 modul D)", () => {
  const originalEnv = process.env.NEXT_PUBLIC_DEMO_LOOM_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEMO_LOOM_URL = originalEnv;
  });

  it("renders Loom iframe with lazy load when NEXT_PUBLIC_DEMO_LOOM_URL is set", () => {
    process.env.NEXT_PUBLIC_DEMO_LOOM_URL =
      "https://www.loom.com/embed/abc123";
    render(<Demo />);
    expect(
      screen.getByRole("heading", { name: /3-minute tour/i }),
    ).toBeInTheDocument();
    const iframe = screen.getByTitle("ABS demo screencast");
    expect(iframe.tagName.toLowerCase()).toBe("iframe");
    expect(iframe).toHaveAttribute("loading", "lazy");
    expect(iframe.getAttribute("src") ?? "").toMatch(/loom\.com\/embed/);
  });

  it("renders the real product gallery (no iframe) when env var is unset", () => {
    delete process.env.NEXT_PUBLIC_DEMO_LOOM_URL;
    render(<Demo />);
    // No iframe, and no "coming soon" dead box — the fallback is now the real
    // panel: a heading that invites a look and the screen tabs beneath it.
    expect(
      screen.queryByTitle("ABS demo screencast"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /see the panel/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /workflows/i }),
    ).toBeInTheDocument();
  });
});
