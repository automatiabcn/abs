import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FAQ from "@/components/FAQ";

describe("FAQ (018 modul C)", () => {
  it("renders all 12 questions (8 baseline + 4 new in 018)", () => {
    render(<FAQ />);
    const items = screen.getAllByRole("term");
    expect(items.length).toBe(12);
  });

  it("includes 4 new questions: vault, refund, GDPR, open source", () => {
    render(<FAQ />);
    expect(screen.getByText(/sops\/age vault/i)).toBeInTheDocument();
    // Turkish "İ" → use exact substring match (Unicode case-folding limitation)
    expect(screen.getByText(/İade nasıl alınır/)).toBeInTheDocument();
    expect(screen.getByText(/gdpr/i)).toBeInTheDocument();
    expect(screen.getByText(/Açık kaynak/)).toBeInTheDocument();
  });
});
