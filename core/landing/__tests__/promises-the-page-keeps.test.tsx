/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Three things the marketing page said that it could not back up.
//
//  1. Its primary button said "Watch the demo" and scrolled to a box reading
//     "Demo video coming soon." The main call to action on the site went
//     nowhere.
//  2. The footer's "Installation guide" pointed at abs.automatiabcn.com, a host
//     that does not resolve.
//  3. It carried three invented testimonials from three invented people, under
//     the heading "Feedback from our first 5 beta testers".
//
// None of these fail a build. All three are read by the person deciding whether
// to trust the product.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Footer from "@/components/Footer";
import Install from "@/components/Install";

function read(relative: string): string {
  return readFileSync(resolve(__dirname, "..", relative), "utf8");
}

describe("promises the page keeps", () => {
  it("the primary button leads to something that exists", () => {
    const page = read("app/page.tsx");
    expect(page).toContain('href: "#install"');
    expect(page).not.toContain('href: "#demo"');
  });

  it("the install section carries the real command, not a placeholder", () => {
    render(<Install />);
    expect(
      screen.getByText(/deploy_hetzner\.sh/, { exact: false }),
    ).toBeInTheDocument();
    // The section that the button now points at has an id to land on.
    expect(document.querySelector("#install")).not.toBeNull();
  });

  it("the footer's install link points at a host that resolves", () => {
    render(<Footer />);
    const link = screen.getByRole("link", { name: /installation guide/i });
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("github.com/automatiabcn/abs"),
    );
    expect(read("components/Footer.tsx")).not.toContain(
      "abs.automatiabcn.com/docs",
    );
  });

  it("no invented testimonials come back", () => {
    const page = read("app/page.tsx");
    expect(page).not.toContain("Quotes");
    expect(() => read("components/Quotes.tsx")).toThrow();
  });
});
