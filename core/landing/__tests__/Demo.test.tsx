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
      screen.getByRole("heading", { name: /3 dakikada/i }),
    ).toBeInTheDocument();
    const iframe = screen.getByTitle("ABS demo screencast");
    expect(iframe.tagName.toLowerCase()).toBe("iframe");
    expect(iframe).toHaveAttribute("loading", "lazy");
    expect(iframe.getAttribute("src") ?? "").toMatch(/loom\.com\/embed/);
  });

  it("renders placeholder copy (no iframe) when env var is unset (Q11-L11-001)", () => {
    delete process.env.NEXT_PUBLIC_DEMO_LOOM_URL;
    render(<Demo />);
    expect(
      screen.queryByTitle("ABS demo screencast"),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/yakında/i)).toBeInTheDocument();
  });
});
