import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConnectPanel from "@/components/ConnectPanel";

const FAKE_RESPONSE = {
  providers: [
    { id: "github", name: "GitHub", auth_method: "oauth" },
    { id: "openai", name: "OpenAI", auth_method: "api_key" },
    { id: "anthropic", name: "Anthropic", auth_method: "api_key" },
  ],
  connected: [
    {
      key_name: "openai_api_key",
      provider: "openai",
      created_at: "2026-04-27T13:00:00Z",
      last_validated_at: "2026-04-27T13:00:00Z",
      last_validated_ok: true,
      last_validated_error: null,
    },
  ],
  count: 1,
};

describe("ConnectPanel (026 modul F)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders title and token input on first paint", () => {
    render(<ConnectPanel />);
    expect(
      screen.getByRole("heading", { name: /Connected Services/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Admin Bearer token/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Load/i }),
    ).toBeDisabled();
  });

  it("disables Load button until token is entered", async () => {
    render(<ConnectPanel />);
    const btn = screen.getByRole("button", { name: /Load/i });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Admin Bearer token/i), "abc");
    expect(btn).not.toBeDisabled();
  });

  it("fetches connected services with Bearer header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(FAKE_RESPONSE), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<ConnectPanel />);
    await userEvent.type(
      screen.getByLabelText(/Admin Bearer token/i),
      "test-token",
    );
    await userEvent.click(screen.getByRole("button", { name: /Load/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/v1/smart-link/connected-services",
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      headers: { Authorization: "Bearer test-token" },
    });
  });

  it("renders provider grid with connected/disconnected indicators", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(FAKE_RESPONSE), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<ConnectPanel />);
    await userEvent.type(
      screen.getByLabelText(/Admin Bearer token/i),
      "test-token",
    );
    await userEvent.click(screen.getByRole("button", { name: /Load/i }));

    expect(await screen.findByTestId("provider-grid")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText(/✓ validated/i)).toBeInTheDocument();
    // GitHub not in connected list → not connected
    const githubText = screen.getAllByText(/not connected/i);
    expect(githubText.length).toBeGreaterThanOrEqual(1);
  });

  it("shows error when API returns 401", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid admin token" }), {
        status: 401,
      }),
    );
    render(<ConnectPanel />);
    await userEvent.type(
      screen.getByLabelText(/Admin Bearer token/i),
      "wrong",
    );
    await userEvent.click(screen.getByRole("button", { name: /Load/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /invalid admin token/i,
    );
  });
});
