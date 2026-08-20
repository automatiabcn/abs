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

import { PRICE, TRIAL_DAYS, TRIAL_LABEL } from "../lib/pricing";

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
  // The emails. This guard read the site and the docs and never the templates,
  // so the expiry warning — the one that arrives three days before a licence
  // lapses, when somebody is deciding whether to keep paying — was still
  // offering the retired Maintenance add-on, in four languages, at $0/year
  // because the price setting defaults to zero and Jinja reads "0" as present.
  const emails = join(REPO, "core", "backend", "app", "email", "templates");
  if (existsSync(emails)) {
    for (const p of globSync("**/*.{html,txt}", { cwd: emails })) {
      files.push(join(emails, p));
    }
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
  // The two-tier subscription that replaced the one-off model and was itself
  // replaced on the same day. Listed so a stale doc saying "$29 a month" is
  // caught the same way "$299 one-time" is.
  /\$29\s*(a|per|\/)\s*month/i,
  /\$19\s*(per|\/)\s*seat/i,
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
    // The Stripe setup script is what creates the price, so it is the closest
    // thing to an authority living in this repo. If someone changes one side,
    // this fails rather than letting the page advertise $5 while the card is
    // billed something else.
    const script = join(REPO, "infra", "scripts", "setup_stripe_products.py");
    if (!existsSync(script)) return;
    const text = readFileSync(script, "utf8");

    const plan = /"name":\s*"ABS Studio",\s*"amount":\s*(\d+)/.exec(text);
    expect(plan, "no ABS Studio price in the Stripe setup").not.toBeNull();
    // Stripe amounts are in cents.
    expect(Number(plan![1])).toBe(PRICE * 100);
  });

  it("there is one plan, not a tier list", () => {
    // The Solo/Team split was retired on 2026-08-03. A second sellable SKU
    // left behind in the Stripe setup would be purchasable through the API
    // even though the page stopped offering it.
    const script = join(REPO, "infra", "scripts", "setup_stripe_products.py");
    if (!existsSync(script)) return;
    const body = readFileSync(script, "utf8");
    const products = body.slice(body.indexOf("PRODUCTS"), body.indexOf("There is no annual"));
    expect((products.match(/"metadata_sku"/g) ?? []).length).toBe(1);
  });

  it("the pricing page reads the number rather than repeating it", () => {
    const tiers = readFileSync(join(LANDING, "components", "PricingTiers.tsx"), "utf8");
    const body = tiers
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");
    // A literal price in the markup is a price that can drift from Stripe.
    expect(body).not.toMatch(/\$\d+\b/);
    expect(body).toContain("PRICE");
  });

  it("the search description says the plan we actually sell", () => {
    const page = readFileSync(join(LANDING, "app", "pricing", "page.tsx"), "utf8");
    const meta = page.slice(page.indexOf("export const metadata"));
    expect(meta).toContain("PRICE");
    expect(meta).not.toMatch(/lifetime/i);
  });

  it("the numbers themselves are sane", () => {
    expect(PRICE).toBeGreaterThan(0);
    expect(TRIAL_DAYS).toBeGreaterThan(0);
    // The prose form and the number are two ways of saying one thing; if they
    // disagree the page contradicts itself in the same paragraph.
    const words = ["zero", "one", "two", "three", "four", "five", "six", "seven"];
    expect(TRIAL_LABEL.toLowerCase()).toContain(words[TRIAL_DAYS] ?? String(TRIAL_DAYS));
  });
});
