import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Pricing from "@/components/Pricing";

// Q6 PA + brand alignment (aa010a7) collapsed the original three-tier
// `<Pricing />` SKU grid (Self-Host / + Maintenance / Managed Cloud)
// into a no-op stub so existing imports keep compiling. The Pilot/PoC
// outreach now lives in `<Contact />`. These tests are the regression
// fence that prevents accidentally re-introducing the deprecated UI.
describe("Pricing — deprecated stub (post Q6 PA)", () => {
  it("renders nothing (component is intentionally a no-op)", () => {
    const { container } = render(<Pricing />);
    expect(container.innerHTML).toBe("");
  });

  it("default export is a function component", () => {
    expect(typeof Pricing).toBe("function");
  });
});
