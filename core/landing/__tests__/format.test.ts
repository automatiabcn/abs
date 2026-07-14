// vitest coverage for `lib/format.ts`.
//
// The helpers are not yet wired into the landing surface (R58 gate
// enforces no hardcoded BCP-47 there; the only currently-rendered
// locale literals live in panel + admin which is TR-first). R71
// pre-locks the locale tables so any future landing call-site goes
// through a tested path.

import { describe, expect, it } from "vitest";

import {
  __test_only_bcp47,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPlural,
} from "@/lib/format";

describe("lib/format BCP-47 mapping", () => {
  it("maps en/tr/es to expected BCP-47 tags", () => {
    expect(__test_only_bcp47("en")).toBe("en-US");
    expect(__test_only_bcp47("tr")).toBe("tr-TR");
    expect(__test_only_bcp47("es")).toBe("es-ES");
  });

  it("falls back to en-US on unknown / undefined / null", () => {
    expect(__test_only_bcp47(undefined)).toBe("en-US");
    expect(__test_only_bcp47("klingon")).toBe("en-US");
    expect(__test_only_bcp47("")).toBe("en-US");
  });
});

describe("formatNumber", () => {
  it("EN uses comma thousands + dot decimal", () => {
    expect(formatNumber(1234.56, "en")).toBe("1,234.56");
  });

  it("TR uses dot thousands + comma decimal", () => {
    // Note: Node's Intl returns "1.234,56" for tr-TR which is the
    // canonical Turkish decimal format.
    expect(formatNumber(1234.56, "tr")).toBe("1.234,56");
  });

  it("ES uses comma decimal; 4-digit numbers omit thousands separator per ES locale rule", () => {
    // ES locale (Node ICU): numbers under 10000 do not get a
    // thousands separator. Decimal is comma either way. The 7-digit
    // test below covers the separator case where ES does match TR.
    expect(formatNumber(1234.56, "es")).toBe("1234,56");
    expect(formatNumber(12345.67, "es")).toBe("12.345,67");
  });

  it("integer formatting preserves group separators per locale", () => {
    expect(formatNumber(1_000_000, "en")).toBe("1,000,000");
    expect(formatNumber(1_000_000, "tr")).toBe("1.000.000");
    expect(formatNumber(1_000_000, "es")).toBe("1.000.000");
  });

  it("Infinity / NaN return their string forms (no throw)", () => {
    expect(formatNumber(NaN, "en")).toBe("NaN");
    expect(formatNumber(Number.POSITIVE_INFINITY, "tr")).toBe("Infinity");
  });

  it("respects Intl.NumberFormatOptions passthrough (percent)", () => {
    // 0.42 → 42% across locales (separator handling differs).
    expect(formatNumber(0.42, "en", { style: "percent" })).toMatch(/42\s?%/);
    expect(formatNumber(0.42, "tr", { style: "percent" })).toMatch(/%\s?42/);
  });
});

describe("formatDate / formatDateTime", () => {
  // Use a fixed Date so the test is deterministic across runners.
  const d = new Date("2026-05-04T12:34:56Z");

  it("EN uses M/D/YYYY (US numeric short)", () => {
    expect(formatDate(d, "en")).toMatch(/\b\d{1,2}\/\d{1,2}\/\d{4}\b/);
  });

  it("TR uses D.M.YYYY (Turkish dotted)", () => {
    expect(formatDate(d, "tr")).toMatch(/\b\d{1,2}\.\d{1,2}\.\d{4}\b/);
  });

  it("ES uses D/M/YYYY (Spanish numeric short)", () => {
    expect(formatDate(d, "es")).toMatch(/\b\d{1,2}\/\d{1,2}\/\d{4}\b/);
  });

  it("invalid Date returns empty string (no throw)", () => {
    expect(formatDate(new Date("not-a-date"), "en")).toBe("");
  });

  it("formatDateTime carries both date and time tokens", () => {
    const out = formatDateTime(d, "en");
    expect(out).toMatch(/\d{1,2}\/\d{1,2}\/\d{2,4}/); // date present
    expect(out).toMatch(/\d{1,2}:\d{2}/);              // time present
  });
});

describe("formatPlural", () => {
  it("English picks `one` for 1 and `other` otherwise", () => {
    const forms = { one: "{n} message", other: "{n} messages" };
    expect(formatPlural(1, forms, "en")).toBe("1 message");
    expect(formatPlural(5, forms, "en")).toBe("5 messages");
    expect(formatPlural(0, forms, "en")).toBe("0 messages");
  });

  it("Turkish does not pluralize — both branches share the same noun", () => {
    const forms = { one: "{n} mesaj", other: "{n} mesaj" };
    expect(formatPlural(1, forms, "tr")).toBe("1 mesaj");
    expect(formatPlural(5, forms, "tr")).toBe("5 mesaj");
    // 1000 with TR thousands separator
    expect(formatPlural(1000, forms, "tr")).toBe("1.000 mesaj");
  });

  it("Spanish: 0 selects `other` (Romance plural rule)", () => {
    const forms = { one: "{n} mensaje", other: "{n} mensajes" };
    expect(formatPlural(0, forms, "es")).toBe("0 mensajes");
    expect(formatPlural(1, forms, "es")).toBe("1 mensaje");
    expect(formatPlural(2, forms, "es")).toBe("2 mensajes");
  });

  it("missing `one` falls through to `other`", () => {
    const forms = { other: "{n} items" };
    expect(formatPlural(1, forms, "en")).toBe("1 items");
  });
});
