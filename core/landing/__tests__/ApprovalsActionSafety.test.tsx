import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import ApprovalCenterPage from "@/app/panel/approvals/page";

// A queue item has no rationale → it renders in the compact table whose single
// action button used to be mislabelled "İncele" (Review) while actually firing
// decide(approve) — an irreversible outbound send from a button that read
// read-only. These tests lock the safety fix: honest label + confirm gate.
const QUEUE_ITEM = {
  id: 7,
  agent_id: "outreach",
  action: "send_email",
  rationale: "",
  evidence: [],
  proposed_message: "",
  risk: "high",
  consent_status: "ok",
  policy_result: "allow",
  status: "pending",
  target_company: "Acme",
  channel: "email",
  created_at: null,
};

const DATA = {
  items: [QUEUE_ITEM],
  pending_total: 1,
  by_risk: { high: 1 },
  tier_stats: { low_auto: 0, medium_pending: 0, high_pending: 1, accept_rate: null },
};

function installFetch(cap: { decide?: any }) {
  return vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/v1/approvals/") && u.endsWith("/decide")) {
      cap.decide = JSON.parse(String(init?.body ?? "{}"));
      return Promise.resolve(
        new Response(JSON.stringify({ action: { status: "sent", reason: "ok" } }), { status: 200 }),
      );
    }
    if (u.includes("/v1/approvals/outbox")) {
      return Promise.resolve(new Response(JSON.stringify({ total: 0, by_status: {}, items: [] }), { status: 200 }));
    }
    if (u.includes("/v1/approvals")) {
      return Promise.resolve(new Response(JSON.stringify(DATA), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
  });
}

describe("approvals action safety", () => {
  let cap: { decide?: any };
  beforeEach(() => { cap = {}; vi.stubGlobal("fetch", installFetch(cap)); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("labels the compact queue action 'Onayla', never the misleading 'İncele'", async () => {
    render(<ApprovalCenterPage />);
    await waitFor(() => expect(screen.getByText("Onayla")).toBeTruthy());
    expect(screen.queryByText("İncele")).toBeNull();
  });

  it("does NOT fire the action when the confirm is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ApprovalCenterPage />);
    const btn = await screen.findByText("Onayla");
    fireEvent.click(btn);
    // give any (wrongly) fired request a tick to land
    await new Promise((r) => setTimeout(r, 30));
    expect(cap.decide).toBeUndefined();
  });

  it("fires decide(approve) only after the confirm is accepted", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ApprovalCenterPage />);
    const btn = await screen.findByText("Onayla");
    fireEvent.click(btn);
    await waitFor(() => expect(cap.decide).toBeTruthy());
    expect(cap.decide).toMatchObject({ decision: "approve" });
  });
});
