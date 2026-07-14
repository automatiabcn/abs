// PricingTiers (4-tier checkout surface) tests.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/billing-flag", () => ({
  BILLING_ENABLED: true,
  BILLING_DISABLED_TITLE: "Billing disabled (test override)",
}));

import PricingTiers from "@/components/PricingTiers";

describe("PricingTiers", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
  });

  it("renders all four tier cards with their prices", () => {
    render(<PricingTiers />);
    expect(screen.getByTestId("pricing-tier-self-host")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-tier-maintenance")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-tier-team-5")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-tier-team-10")).toBeInTheDocument();
    expect(screen.getByText("$299")).toBeInTheDocument();
    expect(screen.getByText("+$49")).toBeInTheDocument();
    expect(screen.getByText("$1,196")).toBeInTheDocument();
    expect(screen.getByText("$2,093")).toBeInTheDocument();
  });

  it("CheckoutButton POSTs to /api/checkout with the right tier", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ url: "https://checkout.stripe.com/x" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    render(<PricingTiers />);
    await userEvent.click(
      screen.getByRole("button", { name: /Buy lifetime/i }),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ tier: "self-host" }),
      }),
    );
  });

  it("highlights the team-5 tier as recommended", () => {
    render(<PricingTiers />);
    const card = screen.getByTestId("pricing-tier-team-5");
    expect(card.className).toContain("ring-blue-500");
  });

  it("renders the four CTAs", () => {
    render(<PricingTiers />);
    expect(
      screen.getByRole("button", { name: /Buy lifetime/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Add maintenance/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Buy 5-seat team/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Buy 10-seat team/i }),
    ).toBeInTheDocument();
  });
});

describe("PricingTiers — billing kill switch", () => {
  it("shows a disabled banner when BILLING_ENABLED is false", async () => {
    vi.resetModules();
    vi.doMock("@/lib/billing-flag", () => ({
      BILLING_ENABLED: false,
      BILLING_DISABLED_TITLE: "Checkout paused — contact support.",
    }));
    const { default: Tiers } = await import("@/components/PricingTiers");
    render(<Tiers />);
    expect(screen.getByTestId("billing-disabled-banner")).toBeInTheDocument();
    expect(
      screen.getByText(/Checkout paused — contact support\./),
    ).toBeInTheDocument();
  });
});
