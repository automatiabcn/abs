import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BetaRequestForm from "@/components/BetaRequestForm";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  mockFetch.mockReset();
});

describe("BetaRequestForm", () => {
  it("renders the email input and submit button", () => {
    render(<BetaRequestForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /request beta access/i }),
    ).toBeInTheDocument();
  });

  it("shows confirmation when /v1/beta/request returns 200 (manual queue)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, auto_approved: false, status: "pending" }),
    });

    render(<BetaRequestForm />);
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /request beta access/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("beta-confirmation")).toBeInTheDocument();
    });
    expect(screen.getByTestId("beta-confirmation").textContent).toMatch(
      /request received|review your request/i,
    );

    const lastCall = mockFetch.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("/v1/beta/request");
    const body = JSON.parse(lastCall?.[1]?.body ?? "{}");
    expect(body.email).toBe("alice@example.com");
    expect(body.lang).toBe("en");
  });

  it("renders an error banner when the API returns 429 duplicate", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 429,
      json: async () => ({ detail: "duplicate_recent_request" }),
    });

    render(<BetaRequestForm />);
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "dup@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /request beta access/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("beta-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("beta-error").textContent).toMatch(
      /already received|try again/i,
    );
  });
});
