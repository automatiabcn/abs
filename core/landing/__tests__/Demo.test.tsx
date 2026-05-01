import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Demo from "@/components/Demo";

describe("Demo (018 modul D)", () => {
  it("renders Loom iframe with lazy load + heading", () => {
    render(<Demo />);
    expect(
      screen.getByRole("heading", { name: /3 dakikada/i }),
    ).toBeInTheDocument();
    const iframe = screen.getByTitle("ABS demo screencast");
    expect(iframe.tagName.toLowerCase()).toBe("iframe");
    expect(iframe).toHaveAttribute("loading", "lazy");
    // src var ve loom URL'sine bakıyor (placeholder veya env)
    expect(iframe.getAttribute("src") ?? "").toMatch(/loom\.com\/embed/);
  });
});
