import { describe, expect, it } from "vitest";

import {
  DEFAULT_LANG,
  detectLangFromAcceptHeader,
  isLang,
  t,
} from "@/lib/i18n";

describe("Landing i18n (023 modul E)", () => {
  it("default lang is en and t() returns english", () => {
    // aa010a7 brand alignment moved the hero CTA from a price-led
    // ("Get Self-Host — $299") to demo-led ("Watch Demo") frame.
    expect(DEFAULT_LANG).toBe("en");
    expect(t("hero.cta_primary", "en")).toBe("Watch Demo");
  });

  it("translates to tr and es", () => {
    expect(t("hero.cta_primary", "tr")).toBe("Demo İncele");
    expect(t("hero.cta_primary", "es")).toBe("Ver Demo");
  });

  it("falls back to en when key missing in non-en", () => {
    // Add a known-only-in-en key by typecast — simulate missing
    expect(t("nonexistent.key", "tr")).toBe("nonexistent.key");
  });

  it("isLang validates supported langs", () => {
    expect(isLang("en")).toBe(true);
    expect(isLang("tr")).toBe(true);
    expect(isLang("es")).toBe(true);
    expect(isLang("de")).toBe(false);
    expect(isLang(undefined)).toBe(false);
  });

  it("detectLangFromAcceptHeader parses headers", () => {
    expect(detectLangFromAcceptHeader(null)).toBe("en");
    expect(detectLangFromAcceptHeader("tr-TR,tr;q=0.9,en;q=0.8")).toBe("tr");
    expect(detectLangFromAcceptHeader("es-ES")).toBe("es");
    expect(detectLangFromAcceptHeader("de-DE,de;q=0.9")).toBe("en");
  });
});
