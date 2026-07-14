import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FAQ from "@/components/FAQ";

describe("FAQ (018 modul C)", () => {
  it("renders every question", () => {
    render(<FAQ />);
    const items = screen.getAllByRole("term");
    expect(items.length).toBe(13);
  });

  it("answers the question a subscription makes people ask", () => {
    // "What happens to my documents if I stop paying?" — the honest answer is
    // "nothing", and a page that does not say so leaves the worst assumption
    // standing.
    render(<FAQ />);
    expect(
      screen.getByText(/What happens when the trial ends, or I cancel\?/i),
    ).toBeInTheDocument();
  });

  it("includes 4 new questions: vault, refund, GDPR, open source", () => {
    render(<FAQ />);
    expect(screen.getByText(/sops\/age vault/i)).toBeInTheDocument();
    expect(screen.getByText(/How do refunds work/i)).toBeInTheDocument();
    expect(screen.getByText(/gdpr/i)).toBeInTheDocument();
    expect(screen.getByText(/Is it open source\?/i)).toBeInTheDocument();
  });
});
