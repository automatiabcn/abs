import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ADMIN_HTML = readFileSync(
  resolve(__dirname, "../../backend/app/static/admin/index.html"),
  "utf-8",
);

describe("Admin dashboard HTML — 032 Modul C", () => {
  it("declares the 6 widgets via data-testid", () => {
    for (const id of [
      "widget-revenue",
      "widget-tiers",
      "widget-security",
      "widget-compliance",
      "widget-beta",
      "widget-vault",
    ]) {
      expect(ADMIN_HTML).toContain(`data-testid="${id}"`);
    }
  });

  it("declares a login form and an error placeholder", () => {
    expect(ADMIN_HTML).toContain('data-testid="login-form"');
    expect(ADMIN_HTML).toContain('data-testid="login-error"');
  });

  it("polls /v1/admin/dashboard with a 30 s interval and POSTs login", () => {
    expect(ADMIN_HTML).toContain("/v1/admin/dashboard");
    expect(ADMIN_HTML).toContain("/v1/admin/login");
    expect(ADMIN_HTML).toContain("REFRESH_MS = 30000");
  });
});
