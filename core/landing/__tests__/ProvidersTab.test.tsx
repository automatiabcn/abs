// Polish round R7 — guard the rewritten Providers tab. Lowercase
// placeholder, missing status badge, plain-text input → all regressions
// the polish round explicitly removed.
//
// De-dup round — provider key *editing* was moved out of this tab into the
// canonical /admin/providers page (ProviderConfigModal), so the Settings tab
// is now a read-only status mirror that delegates via a "Yönet" link. The two
// guards below assert that single-source-of-truth design instead of the
// retired embedded-edit form (no duplicate placeholder map, no key input here).
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

  it("delegates editing to the canonical /admin/providers page", () => {
    // De-dup: the Settings tab no longer embeds an edit form; it links out to
    // the single source of truth so provider config lives in exactly one place.
    expect(SETTINGS_PAGE).toContain('data-test="providers-manage-link"');
    expect(SETTINGS_PAGE).toContain('href="/admin/providers"');
  });

  it("renders a status badge per provider", () => {
    expect(SETTINGS_PAGE).toContain('data-test={`provider-status-${p.id}`}');
    expect(SETTINGS_PAGE).toContain("Yapılandırıldı");
    expect(SETTINGS_PAGE).toContain('"Eksik"');
  });

  it("does not embed a duplicate API key input (editing lives elsewhere)", () => {
    // The retired design rendered a `provider-input-${p.id}` key field here.
    // It now lives only on /admin/providers — guard against the duplicate
    // edit surface reappearing in Settings.
    expect(SETTINGS_PAGE).not.toContain("provider-input-${p.id}");
    expect(SETTINGS_PAGE).not.toContain('type="password"');
  });

  it("does not fall back to lowercase id labels in the row", () => {
    // The previous mock rendered `<code>{p.id}</code>` (lowercase). The
    // rewrite renders `{p.label}` from the backend. If the legacy code
    // path returns this assertion catches it.
    expect(SETTINGS_PAGE).not.toMatch(/<code className="font-mono text-sm">\{p\.id\}<\/code>/);
  });
});
