// Polish round R8 — sample prompt audit. The earlier set leaked the
// founder's internal Slack channel ("#ürün") and a CTO-only doc. Brief
// asks for four neutral openers a paying customer can make sense of.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const CHAT_INDEX = readFileSync(
  resolve(__dirname, "../components/chat/index.tsx"),
  "utf-8",
);

describe("Chat EmptyState — sample prompts", () => {
  it("does not reference the founder's internal Slack channel", () => {
    expect(CHAT_INDEX).not.toContain("#ürün");
    expect(CHAT_INDEX).not.toContain("Slack #");
  });

  it("does not reference the legacy CTO security policy demo", () => {
    expect(CHAT_INDEX).not.toContain("CTO'nun yayınladığı güvenlik");
  });

  it("includes the brief's four customer-facing openers", () => {
    const expected = [
      "İlk projemde sana nasıl yardım edebilirim?",
      "Bu hafta ekibimin yaptığı işleri",
      "Yeni müşteri görüşmesi için hazırlık",
      "/help",
    ];
    for (const phrase of expected) {
      expect(
        CHAT_INDEX.includes(phrase),
        `sample prompts missing phrase: ${phrase}`,
      ).toBe(true);
    }
  });

  it("still defines exactly one SAMPLE_PROMPTS array", () => {
    const matches = CHAT_INDEX.match(/const SAMPLE_PROMPTS\b/g) ?? [];
    expect(matches.length).toBe(1);
  });
});
