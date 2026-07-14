// Q11 Round 24 / L16 — error tile UX consistency.
//
// Static source-level audit: the chat panel and pipeline runner both
// must ship the panel-wide error pattern (Configure + Retry CTAs +
// data-test attributes for Playwright). Catches a regression where
// either component drops the structure to a bare "Hata: {error}".

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("Q11/L16 — error tile UX parity", () => {
  it("chat error tile (Q10-L9-001) ships Configure CTA + role=alert", () => {
    // The panel chat route was split into a thin wrapper
    // (`page.tsx`) plus a dynamically-imported client (`ChatClient.tsx`).
    // The error tile contract moved with the client, not the wrapper.
    const src = read("app/panel/chat/ChatClient.tsx");
    expect(src).toContain('role="alert"');
    expect(src).toContain('data-test="chat-error-tile"');
    expect(src).toContain('data-test="configure-cta"');
    // The tile has to offer a way out, not just name the failure.
    expect(src).toContain("Configure a provider");
  });

  it("pipeline error tile (Q11-L16-001) ships Configure + Retry CTAs", () => {
    const src = read("app/admin/pipelines/page.tsx");
    expect(src).toContain('role="alert"');
    expect(src).toContain('data-test="pipeline-error-tile"');
    expect(src).toContain('data-test="pipeline-configure-cta"');
    expect(src).toContain('data-test="pipeline-retry-cta"');
    expect(src).toContain("Configure a provider");
    expect(src).toContain("Try again");
  });

  it("setError sites name what failed (Q11-L16-002)", () => {
    // meetings/[id] now prefixes errors
    const detail = read("app/panel/meetings/[id]/page.tsx");
    expect(detail).toContain("Could not load this meeting");

    // quota error names what failed instead of a bare "unknown"
    const quota = read("app/panel/quota/page.tsx");
    expect(quota).toContain("Couldn't load usage");
    expect(quota).toContain("unknown error");
    expect(quota).not.toMatch(/setError\([^)]*"unknown"/);
  });
});
