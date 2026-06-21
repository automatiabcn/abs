import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";

import RagPage from "@/app/admin/rag/page";

// codebase tags elements with data-test, not data-testid
configure({ testIdAttribute: "data-test" });

// Panel UX for the unified image+text RAG index: a modality filter
// (All / Docs / Images) that sends `kinds`, and a 🖼️/📄 badge per hit.

const IMAGE_HIT = {
  chunk_id: "c1",
  score: 0.91,
  text: "a red invoice with a blue logo",
  doc_id: "img-1",
  metadata: { kind: "image", source_filename: "invoice.png" },
};

function installFetch(captured: { body?: any; imageQueryUrl?: string }) {
  return vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/v1/rag/query-by-image") && method === "POST") {
      captured.imageQueryUrl = u;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            description: "a pricing table screenshot",
            hits: [IMAGE_HIT],
            elapsed_ms: 2,
          }),
          { status: 200 },
        ),
      );
    }
    if (u.includes("/v1/rag/query") && method === "POST") {
      captured.body = JSON.parse(String(init?.body ?? "{}"));
      return Promise.resolve(
        new Response(JSON.stringify({ query: "x", hits: [IMAGE_HIT], elapsed_ms: 1 }), {
          status: 200,
        }),
      );
    }
    // documents inventory load on mount + anything else
    return Promise.resolve(
      new Response(JSON.stringify({ documents: [], hits: [] }), { status: 200 }),
    );
  });
}

describe("RAG panel — unified image/text UX", () => {
  let captured: { body?: any; imageQueryUrl?: string };
  beforeEach(() => {
    captured = {};
    vi.stubGlobal("fetch", installFetch(captured));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the modality filter with all three scopes", async () => {
    render(<RagPage />);
    expect(await screen.findByTestId("rag-kind-all")).toBeTruthy();
    expect(screen.getByTestId("rag-kind-docs")).toBeTruthy();
    expect(screen.getByTestId("rag-kind-images")).toBeTruthy();
  });

  it("badges an image hit and 'Görsel' filter sends kinds=['image']", async () => {
    render(<RagPage />);
    fireEvent.change(await screen.findByPlaceholderText(/CTO/i), {
      target: { value: "logo" },
    });
    fireEvent.click(screen.getByTestId("rag-kind-images"));
    fireEvent.click(screen.getByTestId("rag-run-query"));

    await waitFor(() => expect(screen.getByTestId("rag-hit-kind")).toBeTruthy());
    expect(screen.getByTestId("rag-hit-kind").textContent).toContain("Görsel");
    expect(screen.getByTestId("rag-hit-kind").textContent).toContain("invoice.png");
    expect(captured.body.kinds).toEqual(["image"]);
  });

  it("image-as-query uploads to /query-by-image and shows the description", async () => {
    render(<RagPage />);
    const input = (await screen.findByTestId(
      "rag-image-query-input",
    )) as HTMLInputElement;
    const file = new File([new Uint8Array([1, 2, 3])], "q.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(screen.getByTestId("rag-image-desc")).toBeTruthy(),
    );
    expect(screen.getByTestId("rag-image-desc").textContent).toContain(
      "pricing table",
    );
    expect(captured.imageQueryUrl).toContain("/v1/rag/query-by-image");
    // the image hit is rendered
    expect(screen.getByTestId("rag-hit-kind").textContent).toContain("Görsel");
  });

  it("'Tümü' filter sends no kinds (docs + images)", async () => {
    render(<RagPage />);
    fireEvent.change(await screen.findByPlaceholderText(/CTO/i), {
      target: { value: "logo" },
    });
    fireEvent.click(screen.getByTestId("rag-run-query"));
    await waitFor(() => expect(captured.body).toBeTruthy());
    expect(captured.body.kinds).toBeUndefined();
  });
});
