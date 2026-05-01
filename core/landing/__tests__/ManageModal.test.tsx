import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ManageModal from "@/components/ManageModal";

const openModal = async () => {
  await userEvent.click(screen.getByRole("button", { name: "Manage" }));
};

const fillEmail = async (value: string) => {
  await userEvent.type(screen.getByLabelText("Email"), value);
};

describe("ManageModal (018 modul E)", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
    vi.restoreAllMocks();
  });

  it("redirects to portal_url on success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ portal_url: "https://billing.stripe.com/test_xyz" }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    render(<ManageModal />);
    await openModal();
    await fillEmail("user@x.co");
    await userEvent.click(screen.getByRole("button", { name: "Portal Aç" }));

    // Resolve microtask: location should be set
    await new Promise((r) => setTimeout(r, 10));
    expect(window.location.href).toBe("https://billing.stripe.com/test_xyz");
  });

  it("shows specific message on 404 (no active license)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({}), { status: 404 }),
    );

    render(<ManageModal />);
    await openModal();
    await fillEmail("missing@x.co");
    await userEvent.click(screen.getByRole("button", { name: "Portal Aç" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /lisans bulunamadı/i,
    );
  });

  it("shows generic error on network failure", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network down"));

    render(<ManageModal />);
    await openModal();
    await fillEmail("user@x.co");
    await userEvent.click(screen.getByRole("button", { name: "Portal Aç" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Network down");
  });
});
