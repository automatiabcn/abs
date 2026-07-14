// Sample prompt audit. An earlier set leaked an internal team channel
// reference and an internal-only doc.
// SAMPLE_PROMPTS retired in favour of the
// 48-prompt library; EmptyState now hydrates hero prompts from
// lib/prompt-library.ts via HERO_PROMPT_IDS. The retired-leak invariant
// on chat/index.tsx still holds; the brief's four legacy openers no
// longer appear in source because the i18n empty-state copy replaced
// them.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { HERO_PROMPT_IDS, PROMPTS } from "@/lib/prompt-library";

const CHAT_INDEX = readFileSync(
  resolve(__dirname, "../components/chat/index.tsx"),
  "utf-8",
);

describe("Chat EmptyState — sample prompts", () => {
  it("does not reference any internal team channel", () => {
    expect(CHAT_INDEX).not.toContain("#ürün");
    expect(CHAT_INDEX).not.toContain("Slack #");
  });

  it("does not reference the legacy CTO security policy demo", () => {
    expect(CHAT_INDEX).not.toContain("CTO'nun yayınladığı güvenlik");
  });

  it("hydrates hero prompts from the prompt library", () => {
    expect(CHAT_INDEX).toContain("HERO_PROMPT_IDS");
    expect(CHAT_INDEX).not.toContain("const SAMPLE_PROMPTS");
  });

  it("hero prompt ids each resolve to a real prompt-library entry", () => {
    expect(HERO_PROMPT_IDS.length).toBe(8);
    for (const id of HERO_PROMPT_IDS) {
      expect(PROMPTS.find((p) => p.id === id)).toBeDefined();
    }
  });
});
