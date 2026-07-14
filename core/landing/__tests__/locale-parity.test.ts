// Locale parity guard. Fails the build if any of the three
// supported locales drifts from the EN canonical key set.
import { describe, expect, it } from "vitest";

import en from "@/locales/en.json";
import tr from "@/locales/tr.json";
import es from "@/locales/es.json";

const enKeys = new Set(Object.keys(en));
const trKeys = new Set(Object.keys(tr));
const esKeys = new Set(Object.keys(es));

describe("locale parity", () => {
  it("EN canonical key set is non-empty", () => {
    expect(enKeys.size).toBeGreaterThan(0);
  });

  it("TR has every EN key", () => {
    const missing = [...enKeys].filter((k) => !trKeys.has(k));
    expect(missing, `TR missing keys: ${missing.join(", ")}`).toEqual([]);
  });

  it("TR has no extra keys beyond EN", () => {
    const extra = [...trKeys].filter((k) => !enKeys.has(k));
    expect(extra, `TR extra keys: ${extra.join(", ")}`).toEqual([]);
  });

  it("ES has every EN key", () => {
    const missing = [...enKeys].filter((k) => !esKeys.has(k));
    expect(missing, `ES missing keys: ${missing.join(", ")}`).toEqual([]);
  });

  it("ES has no extra keys beyond EN", () => {
    const extra = [...esKeys].filter((k) => !enKeys.has(k));
    expect(extra, `ES extra keys: ${extra.join(", ")}`).toEqual([]);
  });

  it("no value is empty string", () => {
    for (const [name, dict] of [
      ["en", en],
      ["tr", tr],
      ["es", es],
    ] as const) {
      const empty = Object.entries(dict)
        .filter(([, v]) => typeof v !== "string" || v.trim() === "")
        .map(([k]) => k);
      // Some keys (e.g. pricing.*.note) are intentionally empty placeholders.
      const ALLOW_EMPTY = new Set([
        "pricing.selfHost.note",
        "pricing.maintenance.note",
        "pricing.managed.note",
      ]);
      const offending = empty.filter((k) => !ALLOW_EMPTY.has(k));
      expect(
        offending,
        `${name} empty values: ${offending.join(", ")}`,
      ).toEqual([]);
    }
  });
});
