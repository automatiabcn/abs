// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// What we say costs money has to be what Stripe charges, and the model we
// retired has to be gone from everywhere a customer reads.
//
// On 2026-08-03 the split was: Stripe took $29/month for one person and
// $19/seat for a team, while three READMEs, seven documents, the site FAQ, the
// pricing page's own search description and the **terms of service** described
// a $299 one-off "Self-Host Lifetime" licence with a $49/year maintenance
// pack. That model had not been purchasable for months. The terms are a
// contract, and they conditioned support on a package nobody could buy.
//
// Nothing was ever "wrong" in the sense of a bad number — the price was
// written down in twenty places, so correcting one taught the others nothing.
// The same shape as the dead download host a day earlier. These tests check
// agreement between files, which is the only thing that was ever broken.

import { describe, expect, it } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { globSync } from "node:fs";
import { join, relative } from "node:path";

import {
  MIN_TEAM_SEATS,
  SOLO_PRICE,
  TEAM_SEAT_PRICE,
  TRIAL_DAYS,
  TRIAL_LABEL,
} from "../lib/pricing";

const LANDING = join(__dirname, "..");
const REPO = join(LANDING, "..", "..");

// Everything a customer can read. Deliberately includes the docs and the
// READMEs: the stale model lived there longest, and a guard over the app alone
// would have passed while the FAQ still sold a lifetime licence.
function customerSurfaces(): string[] {
  const files: string[] = [];
  for (const sub of ["app", "components"]) {
    const dir = join(LANDING, sub);
    if (!existsSync(dir)) continue;
    for (const p of globSync("**/*.tsx", { cwd: dir })) {
      if (p.includes("__tests__")) continue;
      files.push(join(dir, p));
    }
  }
  const docs = join(REPO, "docs");
  if (existsSync(docs)) {
    for (const p of globSync("**/*.md", { cwd: docs })) files.push(join(docs, p));
  }
  for (const name of ["README.md", "README.tr.md", "README.es.md", "SECURITY.md"]) {
    const p = join(REPO, name);
    if (existsSync(p)) files.push(p);
  }
  return files;
}

// The retired model, by the words it is spelled with. Matching on "$299" alone
// would miss "Self-Host Lifetime" and "Maintenance Pack", which is how a
// find-and-replace leaves a page half-corrected.
const RETIRED = [
  /\$299\b/,
  /\$49\s*\/\s*(year|yıl|año)/i,
  /self-host lifetime/i,
  /maintenance pack(age)?/i,
  /bakım paketi/i,
  /lifetime licen[cs]e/i,
  /managed cloud/i,
];

describe("one price, everywhere", () => {
  it("finds the surfaces at all (a green suite over an empty glob proves nothing)", () => {
    expect(customerSurfaces().length).toBeGreaterThan(20);
  });

  it("no customer surface still sells the retired model", () => {
    const offenders: string[] = [];
    for (const file of customerSurfaces()) {
      const text = readFileSync(file, "utf8");
      // A comment naming the retired model is how we remember it was retired,
      // and those comments run to several lines — checking only the first one
      // flagged this repo's own explanation of the fix.
      let inBlock = false;
      for (const [i, line] of text.split("\n").entries()) {
        const t = line.trim();
        const opens = t.includes("{/*") || t.includes("/*");
        const closes = t.includes("*/");
        const wasInBlock = inBlock;
        if (opens && !closes) inBlock = true;
        else if (closes) inBlock = false;
        if (wasInBlock || opens || t.startsWith("//") || t.startsWith("*")) continue;
        for (const pattern of RETIRED) {
          if (pattern.test(line)) {
            offenders.push(`${relative(REPO, file)}:${i + 1}: ${t.slice(0, 90)}`);
            break;
          }
        }
      }
    }
    expect(
      offenders,
      "these describe a product nobody can buy:\n  " + offenders.slice(0, 25).join("\n  "),
    ).toEqual([]);
  });

  it("the page charges what Stripe charges", () => {
    // The Stripe setup script is what creates the prices, so it is the closest
    // thing to an authority that lives in this repo. If someone changes one
    // side, this fails rather than letting the page advertise $29 while the
    // card is billed something else.
    const script = join(REPO, "infra", "scripts", "setup_stripe_products.py");
    if (!existsSync(script)) return;
    const text = readFileSync(script, "utf8");

    const solo = /"name":\s*"ABS Solo",\s*"amount":\s*(\d+)/.exec(text);
    const team = /"name":\s*"ABS Team",\s*"amount":\s*(\d+)/.exec(text);
    expect(solo, "no ABS Solo price in the Stripe setup").not.toBeNull();
    expect(team, "no ABS Team price in the Stripe setup").not.toBeNull();

    // Stripe amounts are in cents.
    expect(Number(solo![1])).toBe(SOLO_PRICE * 100);
    expect(Number(team![1])).toBe(TEAM_SEAT_PRICE * 100);
  });

  it("the pricing page reads the numbers rather than repeating them", () => {
    const tiers = readFileSync(join(LANDING, "components", "PricingTiers.tsx"), "utf8");
    const body = tiers
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");
    // A literal price in the markup is a price that can drift from Stripe.
    expect(body).not.toMatch(/\$29\b/);
    expect(body).not.toMatch(/\$19\b/);
    expect(body).toContain("SOLO_PRICE");
    expect(body).toContain("TEAM_SEAT_PRICE");
  });

  it("the search description says the plan we actually sell", () => {
    const page = readFileSync(join(LANDING, "app", "pricing", "page.tsx"), "utf8");
    const meta = page.slice(page.indexOf("export const metadata"));
    expect(meta).toContain("SOLO_PRICE");
    expect(meta).not.toMatch(/lifetime/i);
  });

  it("the numbers themselves are sane", () => {
    expect(SOLO_PRICE).toBeGreaterThan(TEAM_SEAT_PRICE);
    // Below this, a team costs less than one Solo seat and the plan is
    // arithmetic nonsense.
    expect(MIN_TEAM_SEATS * TEAM_SEAT_PRICE).toBeGreaterThan(SOLO_PRICE);
    expect(TRIAL_DAYS).toBeGreaterThan(0);
    // The prose form and the number are two ways of saying one thing; if they
    // disagree the page contradicts itself in the same paragraph.
    const words = ["zero", "one", "two", "three", "four", "five", "six", "seven"];
    expect(TRIAL_LABEL.toLowerCase()).toContain(words[TRIAL_DAYS] ?? String(TRIAL_DAYS));
  });
});
