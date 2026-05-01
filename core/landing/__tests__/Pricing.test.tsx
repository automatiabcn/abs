import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Pricing from "@/components/Pricing";

describe("Pricing (018 modul B)", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
    vi.restoreAllMocks();
  });

  it("renders 3 SKU cards (Self-Host, Maintenance, Managed Cloud)", () => {
    render(<Pricing />);
    expect(screen.getByText("Self-Host Lifetime")).toBeInTheDocument();
    expect(screen.getByText("+ Maintenance")).toBeInTheDocument();
    expect(screen.getByText("Managed Cloud")).toBeInTheDocument();
    // 14-day refund vurgusu var
    expect(screen.getByText(/14 gün/i)).toBeInTheDocument();
  });

  it("self-host CTA POSTs to /api/checkout and redirects on success", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ url: "https://checkout.stripe.com/sh" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<Pricing />);
    await userEvent.click(screen.getByRole("button", { name: "Self-Host Satın Al" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ tier: "self-host" }),
      }),
    );
    expect(window.location.href).toBe("https://checkout.stripe.com/sh");
  });

  it("renders team-5 and team-10 buttons that hit checkout", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ url: "https://checkout.stripe.com/team5" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<Pricing />);
    expect(screen.getByText("5 seat paketi")).toBeInTheDocument();
    expect(screen.getByText("10 seat paketi")).toBeInTheDocument();

    const teamButtons = screen.getAllByRole("button", { name: "Al" });
    expect(teamButtons.length).toBeGreaterThanOrEqual(2);

    await userEvent.click(teamButtons[0]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        body: JSON.stringify({ tier: "team-5" }),
      }),
    );
  });

  it("shows error when checkout API returns failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "Stripe rate limit" }), {
        status: 502,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<Pricing />);
    await userEvent.click(screen.getByRole("button", { name: "Bakımla Satın Al" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Stripe rate limit");
  });
});
