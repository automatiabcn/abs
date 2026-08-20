import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Footer from "@/components/Footer";

describe("Footer (018 modul F)", () => {
  it("displays Automatia BCN legal entity reference", () => {
    render(<Footer />);
    // The heading is the PRODUCT ("ABS Studio", renamed 08-03); the body is the
    // COMPANY ("Automatia BCN"). This test exists to keep the second one alive
    // through changes to the first — the entity that signs the terms must not
    // disappear in a rename.
    const automatiaHeading = screen.getByRole("heading", {
      name: "ABS Studio",
    });
    expect(automatiaHeading).toBeInTheDocument();
    expect(screen.getAllByText(/Automatia BCN/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Barcelona/)).toBeInTheDocument();
    expect(screen.getByText(/GDPR compliant/)).toBeInTheDocument();
  });

  it("links to /privacy and /terms pages", () => {
    // Brand alignment (aa010a7) collapsed the legacy three-link legal
    // strip down to /privacy + /terms; refund language now lives in
    // the dedicated /refund page (deep link from privacy), not the
    // global footer.
    render(<Footer />);
    const privacy = screen.getByRole("link", { name: /privacy policy/i });
    expect(privacy).toHaveAttribute("href", "/privacy");

    const terms = screen.getByRole("link", { name: /terms of service/i });
    expect(terms).toHaveAttribute("href", "/terms");
  });

  it("links to a mailbox we actually read", () => {
    // Pinned on the promise, not the local part: the footer must offer a way
    // to reach a human, and it must be an address that receives mail. On
    // 08-02 the site pointed at support@ across 63 places while only info@
    // existed — an address that bounces is worse than none, because the
    // reader believes they have asked and then waits.
    render(<Footer />);
    const supportLink = screen.getByRole("link", {
      name: /info@automatiabcn\.com/i,
    });
    expect(supportLink).toHaveAttribute(
      "href",
      "mailto:info@automatiabcn.com",
    );
  });
});
