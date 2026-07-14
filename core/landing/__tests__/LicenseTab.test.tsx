// guard against the hardcoded mock returning. The tab
// must read /v1/license/info and render real values, then expose a usable
// activation form.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SETTINGS_PAGE = readFileSync(
  resolve(__dirname, "../app/admin/settings/page.tsx"),
  "utf-8",
);

describe("LicenseTab — settings page source guard", () => {
  it("does not ship the legacy hardcoded JTI", () => {
    expect(SETTINGS_PAGE).not.toContain("jwt-…12ab34cd");
  });

  it("does not hardcode the Solo tier badge or 2027 expiry", () => {
    expect(SETTINGS_PAGE).not.toMatch(/<Badge>Solo<\/Badge>/);
    expect(SETTINGS_PAGE).not.toContain("2027-04-30");
  });

  it("fetches /v1/license/info to populate the tab", () => {
    expect(SETTINGS_PAGE).toContain('"/v1/license/info"');
  });

  it("posts to /v1/license/activate with a license_key body", () => {
    expect(SETTINGS_PAGE).toContain('"/v1/license/activate"');
    // Object shorthand or explicit key — either spelling counts.
    expect(
      SETTINGS_PAGE.includes("license_key:") ||
        SETTINGS_PAGE.includes('"license_key"'),
    ).toBe(true);
  });

  it("renders a textarea + button for token activation", () => {
    expect(SETTINGS_PAGE).toContain('data-test="license-activation-input"');
    expect(SETTINGS_PAGE).toContain('data-test="license-activate-button"');
  });

  it("declares a JTI mask helper instead of inlining placeholder dots", () => {
    expect(SETTINGS_PAGE).toContain("function maskJti");
  });
});
