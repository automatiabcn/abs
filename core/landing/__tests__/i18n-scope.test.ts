// Q12 Session 8 R58 — L8 i18n scope drift guard.
//
// ABS i18n is intentionally bifurcated:
//   • **Landing surface** (`/`, `/pricing`, `/privacy`, `/terms`, etc.) is
//     fully internationalised via `lib/i18n.ts` + `locales/{en,tr,es}.json`.
//     Default lang is EN per CLAUDE.md ("ürün globale satılır → default
//     İngilizce"). Marketing copy must use `t(key, lang)`.
//   • **Panel + admin + components/chat** is TR-first by design (the
//     self-host operator UI). `tr-TR` Intl formatters and Turkish
//     literals are intentional here.
//
// This test is the regression guard that prevents the line from
// blurring — accidentally adding a hardcoded `"tr-TR"` Intl call on
// the landing surface, or accidentally adding panel strings to the
// global locale dict.
//
// Failure mode this catches: a future PR adds
//   `new Date(...).toLocaleString("tr-TR")` to `app/page.tsx` or
//   `components/Header.tsx`, breaking EN/ES marketing visitors.

import { describe, expect, it } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";

const LANDING_ROOT = path.resolve(__dirname, "..");
// Directories that are TR-first by design — locale hardcodes are OK.
const TR_FIRST_PREFIXES = [
  path.join(LANDING_ROOT, "app", "panel"),
  path.join(LANDING_ROOT, "app", "admin"),
  path.join(LANDING_ROOT, "app", "auth"),
  path.join(LANDING_ROOT, "app", "login"),
  path.join(LANDING_ROOT, "app", "signup"),
  path.join(LANDING_ROOT, "app", "setup"),
  path.join(LANDING_ROOT, "components", "chat"),
  path.join(LANDING_ROOT, "components", "panel"),
  path.join(LANDING_ROOT, "components", "onboarding"),
  path.join(LANDING_ROOT, "__tests__"),
];

// Directories to walk when looking for landing-surface drift.
const LANDING_SCAN_DIRS = [
  path.join(LANDING_ROOT, "app"),
  path.join(LANDING_ROOT, "components"),
];

function isTrFirst(absPath: string): boolean {
  return TR_FIRST_PREFIXES.some((prefix) => absPath.startsWith(prefix + path.sep));
}

function walkTsx(dir: string, accumulator: string[] = []): string[] {
  if (!fs.existsSync(dir)) return accumulator;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkTsx(full, accumulator);
    } else if (entry.isFile() && /\.(tsx|ts)$/.test(entry.name)) {
      accumulator.push(full);
    }
  }
  return accumulator;
}

const HARDCODED_LOCALE_RE = /"(tr-TR|en-US|en-GB|es-ES|es-419)"/g;

describe("i18n scope drift guard (Q12-L8 R58)", () => {
  it("landing-surface files have no hardcoded BCP-47 locale tags", () => {
    const offences: string[] = [];
    for (const root of LANDING_SCAN_DIRS) {
      for (const file of walkTsx(root)) {
        if (isTrFirst(file)) continue;
        const src = fs.readFileSync(file, "utf-8");
        const matches = src.match(HARDCODED_LOCALE_RE);
        if (matches && matches.length > 0) {
          offences.push(
            `${path.relative(LANDING_ROOT, file)} → ${[...new Set(matches)].join(", ")}`,
          );
        }
      }
    }
    expect(
      offences,
      `Landing-surface files must not hardcode BCP-47 locale tags. ` +
        `Use lib/i18n.ts \`t(key, lang)\` for strings and pass the active ` +
        `\`lang\` to Intl formatters. Offenders:\n  ${offences.join("\n  ")}`,
    ).toEqual([]);
  });

  it("locale dict size is locked (size-only regression guard)", () => {
    // We don't assert the exact byte count (translations refine over
    // time) but we do lock the *shape* — every supported locale should
    // load with at least 70 keys and at most 200. A jump outside that
    // window means someone added panel strings to the global dict (or
    // wholesale-deleted marketing copy) and the change should be
    // explicit.
    const en = require("../locales/en.json");
    const tr = require("../locales/tr.json");
    const es = require("../locales/es.json");
    for (const [name, dict] of [
      ["en", en],
      ["tr", tr],
      ["es", es],
    ] as const) {
      const size = Object.keys(dict).length;
      expect(size, `${name} dict size out of [70, 200] band`).toBeGreaterThanOrEqual(70);
      expect(size, `${name} dict size out of [70, 200] band`).toBeLessThanOrEqual(200);
    }
  });

  it("locale dict scope is landing-only (no panel/admin keys)", () => {
    const en = require("../locales/en.json") as Record<string, string>;
    // If the dict ever sprouts a panel/admin/chat key, that's the
    // signal that scope drift has happened. Bail early.
    const PANEL_PREFIXES = ["panel.", "admin.", "chat.", "setup.", "auth."];
    const offenders = Object.keys(en).filter((k) =>
      PANEL_PREFIXES.some((p) => k.startsWith(p)),
    );
    expect(
      offenders,
      `Locale dict should be landing-only. Panel/admin/chat keys must ` +
        `live inline or in a panel-specific dict. Offenders: ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});
