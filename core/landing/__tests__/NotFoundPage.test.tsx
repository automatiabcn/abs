// Polish round R10 — guarantee the global 404 ships in Turkish with
// both return CTAs.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const NOT_FOUND = readFileSync(
  resolve(__dirname, "../app/not-found.tsx"),
  "utf-8",
);

describe("/app/not-found.tsx — global 404", () => {
  it("declares the Turkish title", () => {
    expect(NOT_FOUND).toContain("Sayfa bulunamadı");
  });

  it("uses lang=tr so screen readers pick TR pronunciation", () => {
    expect(NOT_FOUND).toMatch(/lang=["']tr["']/);
  });

  it("links back to both / and /admin/usage", () => {
    expect(NOT_FOUND).toContain('href="/"');
    expect(NOT_FOUND).toContain('href="/admin/usage"');
  });

  it("hides itself from search engines via robots metadata", () => {
    expect(NOT_FOUND).toContain("robots:");
    expect(NOT_FOUND).toContain("index: false");
  });
});
