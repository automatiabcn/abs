import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";

import GraphPage from "@/app/admin/graph/page";
import DashboardPage from "@/app/admin/dashboard/page";
import AgentsPage from "@/app/panel/agents/page";

configure({ testIdAttribute: "data-test" });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── Finding #2: graph NL→Cypher sent the wrong request key ───────────────────
// Frontend POSTed { question } but the backend NLQueryRequest requires `intent`,
// so every "Generate Cipher" click returned HTTP 422 and the feature never worked.
describe("Graph NL→Cypher — request key matches backend contract", () => {
  it("POSTs { intent } (not { question }) to /v1/graph/nl-query", async () => {
    const cap: { body?: string } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL | Request, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/v1/graph/nl-query")) {
          cap.body = String(init?.body ?? "");
          return Promise.resolve(
            new Response(JSON.stringify({ cypher: "MATCH (n) RETURN n LIMIT 1" }), {
              status: 200,
            }),
          );
        }
        // schema fetch on mount
        return Promise.resolve(
          new Response(JSON.stringify({ node_labels: [], relationship_types: [] }), {
            status: 200,
          }),
        );
      }),
    );

    render(<GraphPage />);
    fireEvent.change(await screen.findByTestId("graph-nl-input"), {
      target: { value: "Acme çalışanları" },
    });
    fireEvent.click(screen.getByTestId("graph-nl-run"));

    await waitFor(() => expect(cap.body).toBeTruthy());
    const parsed = JSON.parse(cap.body!);
    expect(parsed.intent).toBe("Acme çalışanları");
    expect(parsed.question).toBeUndefined();
  });
});

// ── Finding #3: tamper warning was dead code ─────────────────────────────────
// Backend emits audit_chain_integrity as the string "ok" | "tampered"; the panel
// tested `=== false`, which a string can never satisfy, so the warning never fired.
describe("Dashboard — audit chain tamper warning fires on a string status", () => {
  function mockDashboard(integrity: "ok" | "tampered") {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ vault: { total_entries: 5, audit_chain_integrity: integrity } }),
            { status: 200 },
          ),
        ),
      ),
    );
  }

  it("shows the tamper warning when integrity is 'tampered'", async () => {
    mockDashboard("tampered");
    render(<DashboardPage />);
    expect(await screen.findByText(/Chain integrity broken/i)).toBeTruthy();
  });

  it("does NOT show the tamper warning when integrity is 'ok'", async () => {
    mockDashboard("ok");
    render(<DashboardPage />);
    // Let the fetch resolve + state settle.
    await screen.findByText(/Vault audit/i);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Chain integrity broken/i)).toBeNull();
  });
});

// ── Finding #1: fabricated "100%" stat ───────────────────────────────────────
// "Structured Output: 100%" sat in the same styled stat grid as real, fetched
// counts, reading as a measured per-tenant compliance rate. It is a design
// invariant, not a measurement — reframed so it no longer masquerades as live.
describe("Agent Registry — structured-output stat is honest, not a fake metric", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ total: 12, approval_gated: 4, categories: [] }),
            { status: 200 },
          ),
        ),
      ),
    );
  });

  it("does not render a fabricated 100% measurement", async () => {
    render(<AgentsPage />);
    await screen.findByText(/Answer format/i);
    expect(screen.queryByText("100%")).toBeNull();
  });
});
