import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Quotes from "@/components/Quotes";

describe("Quotes (018 modul D)", () => {
  it("renders 3 testimonial cards with author + role", () => {
    render(<Quotes />);
    expect(
      screen.getByRole("heading", { name: /what beta users say/i }),
    ).toBeInTheDocument();
    const figures = screen.getAllByRole("figure");
    expect(figures.length).toBe(3);
    expect(screen.getByText(/Murat K\./)).toBeInTheDocument();
    expect(screen.getByText(/Carlos V\./)).toBeInTheDocument();
    expect(screen.getByText(/Asli D\./)).toBeInTheDocument();
  });
});
