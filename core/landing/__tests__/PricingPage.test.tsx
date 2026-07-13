import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import PricingPage from "@/components/PricingPage";

// Q6 PA + brand alignment (aa010a7) collapsed the original three-tier
// pricing cards (Self-Host Lifetime / + Maintenance / Managed Cloud)
// into a single Pilot/PoC contact CTA. The component now ignores the
// `lang` prop entirely so we exercise the surfaces that survived: the
// section testid, the heading, and the mailto CTA.
describe("PricingPage — Pilot/PoC outreach (post Q6 PA)", () => {
  it("renders the Pilot/PoC outreach section", () => {
    render(<PricingPage lang="en" />);
    expect(screen.getByTestId("pricing-page")).toBeInTheDocument();
    expect(screen.getByText(/Pilot \/ PoC call/)).toBeInTheDocument();
  });

  it("ships a mailto CTA to the support inbox", () => {
    render(<PricingPage lang="en" />);
    const cta = screen.getByTestId("pricing-page-cta");
    expect(cta.tagName.toLowerCase()).toBe("a");
    expect(cta.getAttribute("href")).toBe(
      "mailto:support@automatiabcn.com",
    );
  });

  it("shows the Barcelona footer line", () => {
    render(<PricingPage lang="en" />);
    expect(
      screen.getByText(/support@automatiabcn\.com · Barcelona/),
    ).toBeInTheDocument();
  });

  it("renders the same surface regardless of lang prop", () => {
    // Component currently does not branch on `lang` — guard against a
    // silent regression that would re-introduce stale per-locale copy.
    const { rerender } = render(<PricingPage lang="en" />);
    const enHtml = screen.getByTestId("pricing-page").innerHTML;
    rerender(<PricingPage lang="tr" />);
    const trHtml = screen.getByTestId("pricing-page").innerHTML;
    rerender(<PricingPage lang="es" />);
    const esHtml = screen.getByTestId("pricing-page").innerHTML;
    expect(trHtml).toBe(enHtml);
    expect(esHtml).toBe(enHtml);
  });
});
