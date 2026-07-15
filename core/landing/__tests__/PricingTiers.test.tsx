// The pricing surface: a monthly subscription, sold two ways.
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

  it("renders the two plans and what they cost", () => {
    render(<PricingTiers />);
    expect(screen.getByTestId("pricing-tier-solo")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-tier-team")).toBeInTheDocument();
    expect(screen.getByText("$29")).toBeInTheDocument();
    expect(screen.getByText("$19")).toBeInTheDocument();
    expect(screen.getByText("/seat/month")).toBeInTheDocument();
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

  it("multiplies the team price by the seats chosen", async () => {
    render(<PricingTiers />);
    const input = screen.getByRole("spinbutton");
    expect(screen.getByText("$57/month")).toBeInTheDocument(); // 3 × 19

    await userEvent.clear(input);
    await userEvent.type(input, "5");
    expect(screen.getByText("$95/month")).toBeInTheDocument(); // 5 × 19
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
    const [soloCta] = screen.getAllByRole("button", { name: /Subscribe/i });
    await userEvent.click(soloCta);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ tier: "solo", seats: 1 }),
      }),
    );
  });

  it("highlights the team plan", () => {
    render(<PricingTiers />);
    expect(screen.getByTestId("pricing-tier-team").className).toContain(
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
