import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CheckoutButton from "@/components/CheckoutButton";

describe("CheckoutButton", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
  });

  it("redirects to returned Stripe URL on success", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ url: "https://checkout.stripe.com/x" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    render(<CheckoutButton tier="self-host">Self-Host Al</CheckoutButton>);
    await userEvent.click(screen.getByRole("button", { name: "Self-Host Al" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ tier: "self-host" }),
      }),
    );
    expect(window.location.href).toBe("https://checkout.stripe.com/x");
  });

  it("shows error message when API returns error payload", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "Price not configured" }), {
        status: 500,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<CheckoutButton tier="team-5">5 seat</CheckoutButton>);
    await userEvent.click(screen.getByRole("button", { name: "5 seat" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Price not configured",
    );
  });
});
