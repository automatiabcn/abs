// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// The tab icon was still the scaffold's.
//
// Reported live on 2026-08-03: app.automatiabcn.com showed the generic icon in
// the browser tab. `app/favicon.ico` had been a 120-byte blank PNG since the
// project was scaffolded in April and nobody had looked at it — the deploy was
// faithful, the file was empty. It is the one piece of branding a customer sees
// before the page has even rendered, and on a page we are selling from.
//
// A blank icon is the failure that hides: nothing errors, no test fails, and
// the only way to notice is to look at the tab. So it is pinned by size — a
// real 32×32 logo cannot be 120 bytes — rather than by hoping somebody looks.

import { describe, expect, it } from "vitest";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(__dirname, "..");

// The scaffold's placeholder, byte for byte. Anything this small is either
// that file or a blank of its own.
const PLACEHOLDER_BYTES = 120;

function icon(name: string) {
  return join(ROOT, "app", name);
}

describe("the tab icon is ours", () => {
  it("favicon.ico is not the scaffold's blank", () => {
    const size = statSync(icon("favicon.ico")).size;
    expect(size).toBeGreaterThan(PLACEHOLDER_BYTES * 4);
  });

  it("ships an icon and an apple-touch icon", () => {
    for (const name of ["icon.png", "apple-icon.png"]) {
      expect(statSync(icon(name)).size).toBeGreaterThan(PLACEHOLDER_BYTES * 4);
    }
  });

  it("they are real images, not text that got renamed", () => {
    for (const name of ["favicon.ico", "icon.png", "apple-icon.png"]) {
      const head = readFileSync(icon(name)).subarray(0, 8);
      const isPng =
        head[0] === 0x89 && head[1] === 0x50 && head[2] === 0x4e && head[3] === 0x47;
      const isIco = head[0] === 0x00 && head[1] === 0x00 && head[2] === 0x01;
      expect(isPng || isIco, `${name} is neither a PNG nor an ICO`).toBe(true);
    }
  });
});
