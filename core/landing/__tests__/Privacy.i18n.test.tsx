import type { ReactElement } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";

// Next.js 15 made `searchParams` a Promise — the privacy page is now an
// async server component, so we resolve it once and render the JSX
// element it returns instead of letting Testing Library try to render
// the async function as a component.
async function renderPrivacy(lang?: "en" | "tr" | "es") {
  const searchParams = lang ? Promise.resolve({ lang }) : undefined;
  // Calling the async server component directly is exactly what
  // Next.js does in production; cast the prop bag because the type
  // contract uses an opaque PageProps generic.
  const element = await (
    PrivacyPage as unknown as (props: {
      searchParams?: Promise<{ lang?: string }>;
    }) => Promise<ReactElement>
  )({ searchParams });
  return render(element);
}

describe("Privacy page — 030 EN/TR/ES i18n", () => {
  it("renders English by default (?lang missing)", async () => {
    const { container } = await renderPrivacy();
    const main = container.querySelector("main");
    expect(main?.getAttribute("data-lang")).toBe("en");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Privacy Policy",
    );
    expect(container.textContent).toMatch(/Data Controller/);
  });

  it("renders Turkish when ?lang=tr", async () => {
    const { container } = await renderPrivacy("tr");
    expect(container.querySelector("main")?.getAttribute("data-lang")).toBe(
      "tr",
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Gizlilik Politikası",
    );
    expect(container.textContent).toMatch(/Veri Sorumlusu/);
  });

  it("renders Spanish when ?lang=es", async () => {
    const { container } = await renderPrivacy("es");
    expect(container.querySelector("main")?.getAttribute("data-lang")).toBe(
      "es",
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Política de Privacidad",
    );
    expect(container.textContent).toMatch(/Responsable del Tratamiento/);
  });
});
