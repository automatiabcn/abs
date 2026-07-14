/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// PromptLibrary drawer + prompt-library data
// integrity. Five locked-in checks:
//   1. renders Turkish category titles when lang="tr"
//   2. typing into the search box filters prompts by title/description
//   3. clicking a category accordion reveals its prompts
//   4. clicking a prompt card calls onPick with the prompt[lang] string
//   5. data integrity — every (id, lang, field) is non-empty
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { PromptLibrary } from "@/components/chat/PromptLibrary";
import {
  PROMPT_CATEGORIES,
  PROMPTS,
  type PromptLang,
} from "@/lib/prompt-library";

const LANGS: PromptLang[] = ["en", "tr", "es"];
const FIELDS = ["title", "description", "prompt"] as const;

describe("PromptLibrary drawer", () => {
  it("renders Turkish category titles when lang=tr", () => {
    render(<PromptLibrary lang="tr" onPick={() => {}} />);
    const founderTitle = PROMPT_CATEGORIES.find((c) => c.id === "founder")!.title.tr;
    expect(screen.getByText(founderTitle)).toBeInTheDocument();
    const salesTitle = PROMPT_CATEGORIES.find((c) => c.id === "sales")!.title.tr;
    expect(screen.getByText(salesTitle)).toBeInTheDocument();
  });

  it("filters prompts when the user types in the search box", () => {
    const { container } = render(<PromptLibrary lang="en" onPick={() => {}} />);
    const search = screen.getByTestId("prompt-library-search") as HTMLInputElement;
    fireEvent.change(search, { target: { value: "investor update" } });
    // search active → no category toggles rendered
    expect(container.querySelectorAll('[data-test="prompt-library-category"]').length).toBe(0);
    const cards = container.querySelectorAll('[data-test="prompt-card"]');
    expect(cards.length).toBeGreaterThan(0);
    const ids = Array.from(cards).map((c) => c.getAttribute("data-prompt-id"));
    expect(ids).toContain("founder-investor-update");
  });

  it("expands a category when its toggle is clicked", () => {
    const { container } = render(<PromptLibrary lang="en" onPick={() => {}} />);
    fireEvent.click(screen.getByTestId("prompt-library-category-toggle-sales"));
    const salesPrompt = PROMPTS.find((p) => p.id === "sales-cold-outreach")!;
    expect(screen.getByText(salesPrompt.title.en)).toBeInTheDocument();
    // sales card now in the DOM as a prompt-card with the matching id
    const card = container.querySelector('[data-prompt-id="sales-cold-outreach"]');
    expect(card).not.toBeNull();
  });

  it("calls onPick with prompt[lang] when a card is clicked", () => {
    const onPick = vi.fn();
    render(<PromptLibrary lang="tr" onPick={onPick} />);
    fireEvent.click(screen.getByTestId("prompt-card-founder-weekly-review"));
    const expected = PROMPTS.find((p) => p.id === "founder-weekly-review")!.prompt.tr;
    expect(onPick).toHaveBeenCalledWith(expected);
  });

  it("data integrity — 48 prompts × 3 langs × 3 fields all non-empty", () => {
    expect(PROMPTS.length).toBe(48);
    for (const item of PROMPTS) {
      for (const lang of LANGS) {
        for (const field of FIELDS) {
          const value = item[field][lang];
          expect(
            typeof value === "string" && value.length > 0,
            `empty ${field}.${lang} on ${item.id}`,
          ).toBe(true);
        }
      }
      expect(Array.isArray(item.placeholders)).toBe(true);
      expect(typeof item.estTokens).toBe("number");
    }
  });
});
