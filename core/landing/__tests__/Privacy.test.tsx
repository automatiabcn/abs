import type { ReactElement } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";

async function renderPrivacy() {
  // PrivacyPage is now an async Next.js 15 server component, so we
  // resolve it once and render the JSX it returns.
  const element = await (
    PrivacyPage as unknown as (props: {
      searchParams?: Promise<{ lang?: string }>;
    }) => Promise<ReactElement>
  )({});
  return render(element);
}

describe("Privacy page — 029 GDPR exercise sections", () => {
  it("documents GDPR self-service endpoints (export, delete, consent)", async () => {
    await renderPrivacy();
    const section = screen.getByTestId("gdpr-rights-exercise");
    expect(section.textContent).toContain("/v1/me/data-export");
    expect(section.textContent).toContain("/v1/me/account/delete-request");
    expect(section.textContent).toContain("/v1/me/account/delete-confirm");
    expect(section.textContent).toContain("/v1/me/consents");
    expect(section.textContent).toContain("/v1/me/audit-log");
  });

  it("links to subprocessors register and DPA template", async () => {
    await renderPrivacy();
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

  it("mentions the 30-day grace period for account deletion", async () => {
    await renderPrivacy();
    const section = screen.getByTestId("gdpr-rights-exercise");
    expect(section.textContent).toMatch(/30[- ]day/i);
  });
});
