// Polish round R7 — guard the rewritten Providers tab. Lowercase
// placeholder, missing status badge, plain-text input → all regressions
// the polish round explicitly removed.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SETTINGS_PAGE = readFileSync(
  resolve(__dirname, "../app/admin/settings/page.tsx"),
  "utf-8",
);

describe("ProvidersTab — polish round R7 guards", () => {
  it("fetches /v1/admin/providers/status", () => {
    expect(SETTINGS_PAGE).toContain('"/v1/admin/providers/status"');
  });

  it("declares a placeholder map keyed by every cascade provider id", () => {
    expect(SETTINGS_PAGE).toContain("PROVIDER_PLACEHOLDER");
    for (const id of ["groq", "cerebras", "cloudflare", "gemini", "cohere", "anthropic"]) {
      expect(
        SETTINGS_PAGE.includes(`${id}: "`),
        `placeholder map missing entry for ${id}`,
      ).toBe(true);
    }
  });

  it("renders a status badge per provider", () => {
    expect(SETTINGS_PAGE).toContain('data-test={`provider-status-${p.id}`}');
    expect(SETTINGS_PAGE).toContain("Yapılandırıldı");
    expect(SETTINGS_PAGE).toContain('"Eksik"');
  });

  it("uses a password input for the API key field", () => {
    // Multiple Inputs in the file; check ProvidersTab section by data-test.
    expect(SETTINGS_PAGE).toMatch(
      /data-test=\{`provider-input-\${p\.id}`\}[\s\S]*?type="password"|type="password"[\s\S]*?data-test=\{`provider-input-\${p\.id}`\}/,
    );
  });

  it("does not fall back to lowercase id labels in the row", () => {
    // The previous mock rendered `<code>{p.id}</code>` (lowercase). The
    // rewrite renders `{p.label}` from the backend. If the legacy code
    // path returns this assertion catches it.
    expect(SETTINGS_PAGE).not.toMatch(/<code className="font-mono text-sm">\{p\.id\}<\/code>/);
  });
});
