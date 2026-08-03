// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// A page title says the product's name once, and the layout is the one that
// says it.
//
// The rename on 2026-08-03 made this visible: the title template appends
// "· ABS Studio", and pages that had hard-coded the old suffix themselves
// suddenly read "Pricing — ABS Studio · ABS Studio". Seen on the live site
// immediately after deploying, not in any test — a stutter is not an error,
// it is just embarrassing, on the tab of the page we sell from.
//
// The rule that prevents it: a page sets what IT is, the layout adds who we
// are. So no page metadata may carry the product name, and none may pin an
// `absolute` title that bypasses the template.

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { globSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = join(__dirname, "..");
const APP = join(ROOT, "app");

const PRODUCT = "ABS Studio";

// The product's own front page is the one place the full name belongs, and the
// one place `absolute` is right: "Overview · ABS Studio" would be a worse tab
// than "ABS Studio — an AI code editor that runs on your machine". Every other
// page describes itself and lets the layout say who we are.
const FRONT_PAGE = "app/studio/page.tsx";

/** Every `title:` line in a page's exported metadata. */
function titleLines(source: string): string[] {
  return source
    .split("\n")
    .filter((line) => /^\s*title:\s/.test(line))
    // `title:` also appears in component prop types and data shapes; only the
    // ones with a string literal are metadata worth checking.
    .filter((line) => line.includes('"') || line.includes("absolute"));
}

const pages = globSync("**/page.tsx", { cwd: APP }).map((p) => join(APP, p));

describe("titles say the product name once", () => {
  it("finds the pages at all (a green suite over an empty glob proves nothing)", () => {
    expect(pages.length).toBeGreaterThan(20);
  });

  it("no page names the product in its own title", () => {
    const offenders: string[] = [];
    for (const file of pages) {
      if (relative(ROOT, file) === FRONT_PAGE) continue;
      for (const line of titleLines(readFileSync(file, "utf8"))) {
        if (line.includes(PRODUCT)) {
          offenders.push(`${relative(ROOT, file)}: ${line.trim()}`);
        }
      }
    }
    expect(offenders, "the layout appends the name; these would say it twice").toEqual(
      [],
    );
  });

  it("no page bypasses the template with an absolute title", () => {
    const offenders: string[] = [];
    for (const file of pages) {
      if (relative(ROOT, file) === FRONT_PAGE) continue;
      for (const line of titleLines(readFileSync(file, "utf8"))) {
        if (line.includes("absolute")) {
          offenders.push(`${relative(ROOT, file)}: ${line.trim()}`);
        }
      }
    }
    expect(offenders, "an absolute title drifts the moment the name changes").toEqual(
      [],
    );
  });

  it("the exception is a real page, not a stale path", () => {
    // An exemption pointing at a file that no longer exists is an exemption
    // that quietly covers nothing — or worse, that somebody renamed around.
    expect(pages.map((p) => relative(ROOT, p))).toContain(FRONT_PAGE);
  });

  it("the layout is the one that carries the name", () => {
    const layout = readFileSync(join(APP, "layout.tsx"), "utf8");
    expect(layout).toContain(`template: "%s · ${PRODUCT}"`);
  });
});
