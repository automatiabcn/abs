import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";

import ProviderKeysPage from "@/app/admin/provider-keys/page";

configure({ testIdAttribute: "data-test" });

const ROWS = [
  { provider: "groq", owner_type: "org", owner_id: "default",
    created_at: null, updated_at: null, last_validated_ok: true },
];

function installFetch(cap: { post?: any; test?: any }) {
  return vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.endsWith("/v1/admin/provider-keys") && method === "GET") {
      return Promise.resolve(new Response(JSON.stringify({ tenant: "default", keys: ROWS }), { status: 200 }));
    }
    if (u.endsWith("/v1/admin/provider-keys") && method === "POST") {
      cap.post = JSON.parse(String(init?.body ?? "{}"));
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    }
    if (u.endsWith("/v1/admin/provider-keys/test") && method === "POST") {
      cap.test = JSON.parse(String(init?.body ?? "{}"));
      return Promise.resolve(new Response(JSON.stringify({ ok: true, provider: "groq" }), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
  });
}

describe("BYOK provider-keys panel", () => {
  let cap: { post?: any; test?: any };
  beforeEach(() => { cap = {}; vi.stubGlobal("fetch", installFetch(cap)); });
  afterEach(() => vi.unstubAllGlobals());

  it("lists stored keys with a validated badge", async () => {
    render(<ProviderKeysPage />);
    await waitFor(() => expect(screen.getByTestId("pk-row")).toBeTruthy());
    expect(screen.getByTestId("pk-validated")).toBeTruthy();
  });

  it("saves a new key with the chosen provider + scope", async () => {
    render(<ProviderKeysPage />);
    await screen.findByTestId("pk-row");
    fireEvent.change(screen.getByTestId("pk-value"), { target: { value: "gsk_new" } });
    fireEvent.click(screen.getByTestId("pk-save"));
    await waitFor(() => expect(cap.post).toBeTruthy());
    expect(cap.post).toMatchObject({ provider: "groq", owner_type: "org", value: "gsk_new" });
  });

  it("pre-save probe hits /test with the typed value and shows the result", async () => {
    render(<ProviderKeysPage />);
    await screen.findByTestId("pk-row");
    fireEvent.change(screen.getByTestId("pk-value"), { target: { value: "gsk_probe" } });
    fireEvent.click(screen.getByTestId("pk-probe"));
    await waitFor(() => expect(screen.getByTestId("pk-probe-result")).toBeTruthy());
    expect(cap.test).toMatchObject({ provider: "groq", value: "gsk_probe" });
    expect(screen.getByTestId("pk-probe-result").textContent).toContain("works");
  });
});
