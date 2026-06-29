import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";

import RagPage from "@/app/admin/rag/page";

configure({ testIdAttribute: "data-test" });

const DOC = { id: "doc-1", filename: "report.pdf", chunks: 5, size_bytes: 2048 };

function installFetch(cap: { deleted?: string }) {
  return vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/v1/rag/documents/") && method === "DELETE") {
      cap.deleted = u;
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    }
    // documents inventory on mount
    return Promise.resolve(
      new Response(JSON.stringify({ documents: [DOC], hits: [] }), { status: 200 }),
    );
  });
}

describe("RAG panel — honest quality targets + delete confirm", () => {
  let cap: { deleted?: string };
  beforeEach(() => { cap = {}; vi.stubGlobal("fetch", installFetch(cap)); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("frames RAG quality numbers as configured targets, not fabricated live values", async () => {
    render(<RagPage />);
    // The honest framing: targets/thresholds + a "hedef" tag.
    expect(await screen.findByText(/Kalite hedefleri/i)).toBeTruthy();
    expect(screen.getByText("≥ 0.85")).toBeTruthy();
    // The old fabricated "current" values must be gone.
    expect(screen.queryByText("0.91")).toBeNull();
    expect(screen.queryByText("2.1%")).toBeNull();
  });

  it("does NOT delete a document when the confirm is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<RagPage />);
    const del = await screen.findByTestId("rag-doc-delete");
    fireEvent.click(del);
    await new Promise((r) => setTimeout(r, 30));
    expect(cap.deleted).toBeUndefined();
  });

  it("deletes only after the confirm is accepted", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<RagPage />);
    const del = await screen.findByTestId("rag-doc-delete");
    fireEvent.click(del);
    await waitFor(() => expect(cap.deleted).toBeTruthy());
    expect(cap.deleted).toContain("/v1/rag/documents/doc-1");
  });
});
