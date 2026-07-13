import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";

import LeadsPage from "@/app/panel/leads/page";

// the codebase tags elements with data-test, not data-testid
configure({ testIdAttribute: "data-test" });

// Repo audit round (Group D): a failed create() used to clear the form and
// refresh as if it had succeeded — the user saw a "saved" UI for a lead that
// was never created. It must now surface an error and keep the form intact.

function mockFetch(postStatus: number) {
  return vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.endsWith("/v1/leads") && method === "GET") {
      return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), { status: 200 }),
      );
    }
    if (u.endsWith("/v1/leads") && method === "POST") {
      return Promise.resolve(new Response("nope", { status: postStatus }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
}

describe("Leads create error handling", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch(500));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces an error and keeps the form when create fails", async () => {
    render(<LeadsPage />);

    // open the manual-entry form
    fireEvent.click(await screen.findByTestId("lead-add-toggle"));
    const nameInput = (await screen.findByTestId(
      "lead-field-name",
    )) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "Demirel Yapı A.Ş." } });

    fireEvent.click(screen.getByTestId("lead-create-submit"));

    // error is shown
    await waitFor(() =>
      expect(screen.getByText(/could not create the lead/i)).toBeTruthy(),
    );
    // form was NOT cleared — the typed value survives the failure
    expect(nameInput.value).toBe("Demirel Yapı A.Ş.");
  });
});
