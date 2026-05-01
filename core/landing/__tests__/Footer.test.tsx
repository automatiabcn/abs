import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Footer from "@/components/Footer";

describe("Footer (018 modul F)", () => {
  it("displays Automatia BCN legal entity reference", () => {
    render(<Footer />);
    // Heading h2 "Automatia ABS" + footer body "Automatia BCN" (in <strong>)
    const automatiaHeading = screen.getByRole("heading", {
      name: "Automatia ABS",
    });
    expect(automatiaHeading).toBeInTheDocument();
    expect(screen.getAllByText(/Automatia BCN/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Barcelona/)).toBeInTheDocument();
    expect(screen.getByText(/GDPR uyumlu/)).toBeInTheDocument();
  });

  it("links to /privacy, /terms, /refund pages", () => {
    render(<Footer />);
    const privacy = screen.getByRole("link", { name: /gizlilik politikası/i });
    expect(privacy).toHaveAttribute("href", "/privacy");

    const terms = screen.getByRole("link", { name: /kullanım koşulları/i });
    expect(terms).toHaveAttribute("href", "/terms");

    // Turkish "İade" — case folding on Turkish I is non-trivial; use exact prefix
    const refund = screen.getByRole("link", { name: /İade politikası/ });
    expect(refund).toHaveAttribute("href", "/refund");
  });

  it("links to support email", () => {
    render(<Footer />);
    const supportLink = screen.getByRole("link", {
      name: /support@automatiabcn\.com/i,
    });
    expect(supportLink).toHaveAttribute(
      "href",
      "mailto:support@automatiabcn.com",
    );
  });
});
