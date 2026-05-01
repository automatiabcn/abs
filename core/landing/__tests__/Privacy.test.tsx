import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";

describe("Privacy page — 029 GDPR exercise sections", () => {
  it("documents GDPR self-service endpoints (export, delete, consent)", () => {
    render(<PrivacyPage />);
    const section = screen.getByTestId("gdpr-rights-exercise");
    expect(section.textContent).toContain("/v1/me/data-export");
    expect(section.textContent).toContain("/v1/me/account/delete-request");
    expect(section.textContent).toContain("/v1/me/account/delete-confirm");
    expect(section.textContent).toContain("/v1/me/consents");
    expect(section.textContent).toContain("/v1/me/audit-log");
  });

  it("links to subprocessors register and DPA template", () => {
    render(<PrivacyPage />);
    const section = screen.getByTestId("gdpr-subprocessors-link");
    const links = section.querySelectorAll("a");
    const hrefs = Array.from(links).map((a) => a.getAttribute("href"));
    expect(
      hrefs.some((h) => h && h.endsWith("docs/legal/subprocessors.md")),
    ).toBe(true);
    expect(
      hrefs.some((h) => h && h.endsWith("docs/legal/dpa-template.md")),
    ).toBe(true);
  });

  it("mentions the 30-day grace period for account deletion", () => {
    render(<PrivacyPage />);
    const section = screen.getByTestId("gdpr-rights-exercise");
    expect(section.textContent).toMatch(/30[- ]day/i);
  });
});
