/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Two pages, one fact. On 2026-08-28 /pricing said "the server download are
// ready now" (a Vercel env string) while /download said "No build has been
// published yet" (derived from RELEASE). The reason a buyer sees must come
// from the same place the download page reads.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { BILLING_DISABLED_TITLE } from "@/lib/billing-flag";
import { RELEASE } from "@/lib/downloads";

function read(relative: string): string {
  return readFileSync(resolve(__dirname, "..", relative), "utf8");
}

describe("pricing and download agree about whether a build exists", () => {
  it("while nothing is published, the checkout notice says so and ignores the env text", () => {
    if (RELEASE !== null) return; // a release exists: the env text is allowed again
    expect(BILLING_DISABLED_TITLE).toMatch(/Nothing is published yet/);
    expect(BILLING_DISABLED_TITLE).not.toMatch(/ready now/i);
  });

  it("the notice is derived from RELEASE in the source, not only from the env", () => {
    const flag = read("lib/billing-flag.ts");
    expect(flag).toContain('import { RELEASE } from "@/lib/downloads"');
    expect(flag).toMatch(/RELEASE === null\s*\?/);
  });

  it("the pricing bullets do not claim that nothing ever reaches us", () => {
    const tiers = read("components/PricingTiers.tsx");
    const bullets = tiers.slice(tiers.indexOf("const BULLETS"), tiers.indexOf("];", tiers.indexOf("const BULLETS")));
    expect(bullets).not.toMatch(/no data of yours ever reaches us/);
    expect(bullets).toMatch(/your code, documents and prompts never leave it/);
  });

  it("every locale's privacy text says when the licence checks in and what it never carries", () => {
    for (const [file, needle] of [
      ["locales/en.json", "never includes your code"],
      ["locales/es.json", "nunca incluye su código"],
      ["locales/es-privacy.json", "nunca incluye su código"],
      ["locales/tr.json", "asla içermez"],
    ] as const) {
      const json = JSON.parse(read(file)) as Record<string, string>;
      expect(json["privacy.dataCollected.license"], file).toContain(needle);
    }
  });
});
