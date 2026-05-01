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

import PricingPage from "@/components/PricingPage";

describe("PricingPage (T-061)", () => {
  it("renders English copy by default", () => {
    render(<PricingPage lang="en" />);
    expect(screen.getByText("Pricing")).toBeInTheDocument();
    expect(screen.getByText("Self-Host Lifetime")).toBeInTheDocument();
    expect(screen.getByText("+ Maintenance")).toBeInTheDocument();
    expect(screen.getByText("Managed Cloud")).toBeInTheDocument();
  });

  it("renders Turkish copy when lang=tr", () => {
    render(<PricingPage lang="tr" />);
    expect(screen.getByText("Fiyatlandırma")).toBeInTheDocument();
    expect(screen.getByText("Self-Host (Ömür Boyu)")).toBeInTheDocument();
    expect(screen.getByText("Yönetilen Bulut")).toBeInTheDocument();
  });

  it("renders Spanish copy when lang=es", () => {
    render(<PricingPage lang="es" />);
    expect(screen.getByText("Precios")).toBeInTheDocument();
    expect(screen.getByText("Self-Host de por vida")).toBeInTheDocument();
    expect(screen.getByText("Cloud gestionado")).toBeInTheDocument();
  });

  it("shows the three plan cards with stable test ids", () => {
    render(<PricingPage lang="en" />);
    expect(screen.getByTestId("pricing-plan-selfHost")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-plan-maintenance")).toBeInTheDocument();
    expect(screen.getByTestId("pricing-plan-managed")).toBeInTheDocument();
  });

  it("disables managed-cloud CTA (waitlist)", () => {
    render(<PricingPage lang="en" />);
    const managedCard = screen.getByTestId("pricing-plan-managed");
    const cta = managedCard.querySelector("button[disabled]");
    expect(cta).not.toBeNull();
    expect(cta?.textContent?.trim()).toBe("Join Waitlist");
  });

  it("renders the refund notice in the active language", () => {
    const { rerender } = render(<PricingPage lang="en" />);
    expect(screen.getByText(/14-day no-questions refund/)).toBeInTheDocument();

    rerender(<PricingPage lang="tr" />);
    expect(screen.getByText(/14 gün koşulsuz iade/)).toBeInTheDocument();

    rerender(<PricingPage lang="es" />);
    expect(screen.getByText(/14 días de devolución/)).toBeInTheDocument();
  });
});
