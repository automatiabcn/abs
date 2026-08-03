// The pricing surface: one plan, $5 a month.
//
// This tested two cards and a seat multiplier until 2026-08-03. The split is
// gone, and the price comes from lib/pricing.ts — asserting the literal "$29"
// here is what let a page and a Stripe product drift apart in the first place,
// so the expected number is derived rather than typed.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/billing-flag", () => ({
  BILLING_ENABLED: true,
  BILLING_DISABLED_TITLE: "Billing disabled (test override)",
}));

import PricingTiers from "@/components/PricingTiers";
import { PRICE } from "@/lib/pricing";

describe("PricingTiers", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
  });

  it("renders one plan and what it costs", () => {
    render(<PricingTiers />);
    expect(screen.getByTestId("pricing-tier-solo")).toBeInTheDocument();
    expect(screen.getByText(`$${PRICE}`)).toBeInTheDocument();
    expect(screen.getByText("/month")).toBeInTheDocument();
  });

  it("offers no second tier and no seat picker", () => {
    // A leftover seat control would post a seat count to a checkout that no
    // longer prices by seat.
    render(<PricingTiers />);
    expect(screen.queryByTestId("pricing-tier-team")).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("says the trial is free and needs no card", () => {
    render(<PricingTiers />);
    expect(screen.getByText(/Seven days free, no card/i)).toBeInTheDocument();
  });

  it("promises the customer's data outlives the subscription", () => {
    // The page must not imply that an unpaid invoice takes someone's documents
    // away — it does not, and saying so plainly is the whole point.
    render(<PricingTiers />);
    expect(
      screen.getByText(/documents, meetings and keys stay on your server/i),
    ).toBeInTheDocument();
  });

  it("posts the plan and the seat count to checkout", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ url: "https://checkout.stripe.com/x" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    render(<PricingTiers />);
    await userEvent.click(screen.getByRole("button", { name: /Subscribe/i }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ tier: "solo", seats: 1 }),
      }),
    );
  });

  it("highlights the plan", () => {
    render(<PricingTiers />);
    expect(screen.getByTestId("pricing-tier-solo").className).toContain(
      "ring-primary",
    );
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
