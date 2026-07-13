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
