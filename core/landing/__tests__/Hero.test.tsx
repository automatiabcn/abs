import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import Hero from "@/components/Hero";

describe("Hero (premium 018)", () => {
  it("renders SVG illustration, title, subtitle and both CTAs", () => {
    render(
      <Hero
        title="Test başlığı"
        subtitle="Alt metin"
        primaryCta={{ text: "Birincil", href: "#pricing" }}
        secondaryCta={{ text: "İkincil", href: "#features" }}
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "Test başlığı" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alt metin")).toBeInTheDocument();

    // Premium SVG illustration var (018 — modul A)
    const svg = screen.getByRole("img", {
      name: /self-host ai orchestration illustration/i,
    });
    expect(svg.tagName.toLowerCase()).toBe("svg");

    const primary = screen.getByRole("link", { name: "Birincil" });
    expect(primary).toHaveAttribute("href", "#pricing");

    const secondary = screen.getByRole("link", { name: "İkincil" });
    expect(secondary).toHaveAttribute("href", "#features");
  });
});
