/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Guards the two failure modes that made the old styling silently wrong.
//
// Both were invisible: a Tailwind utility built from a colour key that does not
// exist produces no CSS rule and no error, so `variant="destructive"` rendered
// an unstyled button across twenty-five call sites for months. And a colour
// handed to Tailwind as a finished `var(--x)` string has no channels left to
// compose an alpha onto, so every `bg-card/60` in the panel — around 190 of
// them — would have rendered nothing at all.
//
// Neither can be caught by looking at the page: you have to know the colour was
// meant to be there.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import config from "../tailwind.config";

const TOKENS_CSS = readFileSync(join(__dirname, "..", "app", "tokens.css"), "utf8");

type ColourValue = string | Record<string, string>;

function flatten(colors: Record<string, ColourValue>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(colors)) {
    if (typeof value === "string") {
      out[key] = value;
      continue;
    }
    for (const [sub, subValue] of Object.entries(value)) {
      out[sub === "DEFAULT" ? key : `${key}-${sub}`] = subValue;
    }
  }
  return out;
}

const COLOURS = flatten(
  (config.theme?.extend?.colors ?? {}) as Record<string, ColourValue>,
);

describe("design tokens", () => {
  it("defines every colour the components ask for", () => {
    // The set Button, StatCard, StatusPill and the panel chrome depend on.
    const required = [
      "canvas",
      "foreground",
      "card",
      "surface",
      "surface-raised",
      "surface-sunken",
      "primary",
      "primary-hover",
      "primary-soft",
      "primary-foreground",
      "secondary",
      "secondary-foreground",
      "accent",
      "accent-foreground",
      "muted",
      "muted-foreground",
      "subtle",
      "destructive",
      "destructive-soft",
      "destructive-foreground",
      "success",
      "success-soft",
      "warning",
      "warning-soft",
      "info",
      "info-soft",
      "border",
      "border-soft",
      "border-strong",
      "ring",
    ];

    const missing = required.filter((name) => !(name in COLOURS));
    expect(missing).toEqual([]);
  });

  it("keeps every colour opacity-capable", () => {
    // `<alpha-value>` is what lets `bg-card/60` resolve. Drop it from a colour
    // and every opacity-modified utility on that colour stops emitting CSS.
    const notComposable = Object.entries(COLOURS)
      .filter(([, value]) => !value.includes("<alpha-value>"))
      .map(([name]) => name);

    expect(notComposable).toEqual([]);
  });

  it("backs every Tailwind colour with a channel triple in tokens.css", () => {
    // A var() Tailwind names but tokens.css never declares resolves to nothing,
    // and the utility renders transparent rather than failing.
    const referenced = new Set<string>();
    for (const value of Object.values(COLOURS)) {
      const match = value.match(/var\((--abs-[a-z-]+)\)/);
      if (match) referenced.add(match[1]);
    }

    const undeclared = [...referenced].filter(
      (name) => !TOKENS_CSS.includes(`${name}:`),
    );
    expect(undeclared).toEqual([]);
  });

  // Contrast is a property of a *pairing*, and the pairings are fixed by the
  // components: subtle labels sit on raised surfaces, a teal pill carries teal
  // text. The first pass of this palette was chosen by eye and three of these
  // landed between 3.5:1 and 4.5:1 — pleasant, and below AA for the small text
  // they exist to set. Ratios are cheap to compute and impossible to eyeball,
  // so they are asserted rather than trusted.
  describe("contrast", () => {
    const channels = (block: string, token: string): [number, number, number] => {
      const match = block.match(new RegExp(`--abs-${token}-rgb:\\s*([\\d\\s]+);`));
      if (!match) throw new Error(`token not found: --abs-${token}-rgb`);
      const parts = match[1].trim().split(/\s+/).map(Number);
      return [parts[0], parts[1], parts[2]];
    };

    // WCAG 2.1 relative luminance.
    const luminance = ([r, g, b]: [number, number, number]) => {
      const lin = (c: number) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    };

    const ratio = (
      fg: [number, number, number],
      bg: [number, number, number],
    ) => {
      const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
      return (hi + 0.05) / (lo + 0.05);
    };

    const lightBlock = TOKENS_CSS.split(":root {")[1]?.split("}")[0] ?? "";
    const darkBlock = TOKENS_CSS.split(":root.dark {")[1]?.split("}")[0] ?? "";

    // Every pairing the components actually render, in both themes.
    const PAIRINGS: [string, string][] = [
      ["fg", "canvas"],
      ["fg", "surface"],
      ["fg", "surface-raised"],
      ["fg-muted", "canvas"],
      ["fg-muted", "surface"],
      ["fg-muted", "surface-raised"],
      ["fg-subtle", "canvas"],
      ["fg-subtle", "surface"],
      ["fg-subtle", "surface-raised"],
      ["brand", "surface"],
      ["brand", "brand-soft"],
      ["brand-fg", "brand"],
      ["success", "success-soft"],
      ["warning", "warning-soft"],
      ["danger", "danger-soft"],
      ["info", "info-soft"],
    ];

    for (const [theme, block] of [
      ["light", lightBlock],
      ["dark", darkBlock],
    ] as const) {
      it(`meets AA (4.5:1) for every text pairing in ${theme}`, () => {
        // Dark restates only what changes; anything it omits it inherits.
        const resolve = (token: string) => {
          try {
            return channels(block, token);
          } catch {
            return channels(lightBlock, token);
          }
        };

        const failures = PAIRINGS.map(([fg, bg]) => ({
          pairing: `${fg} on ${bg}`,
          ratio: Number(ratio(resolve(fg), resolve(bg)).toFixed(2)),
        })).filter((result) => result.ratio < 4.5);

        expect(failures).toEqual([]);
      });
    }
  });

  it("gives light and dark a value for the same tokens", () => {
    // A token defined only in light leaves dark inheriting a colour built for a
    // white ground — the failure mode that stranded the sidebar logo dark-on-dark.
    const lightBlock = TOKENS_CSS.split(":root {")[1]?.split("}")[0] ?? "";
    const darkBlock = TOKENS_CSS.split(":root.dark {")[1]?.split("}")[0] ?? "";

    const names = (block: string) =>
      new Set(
        [...block.matchAll(/(--abs-[a-z-]+-rgb):/g)].map((match) => match[1]),
      );

    const light = names(lightBlock);
    const dark = names(darkBlock);
    expect(light.size).toBeGreaterThan(0);

    // `ring` is an alias of brand in both themes, so dark need not restate it.
    const missingInDark = [...light].filter(
      (name) => !dark.has(name) && name !== "--abs-ring-rgb",
    );
    expect(missingInDark).toEqual([]);
  });
});
