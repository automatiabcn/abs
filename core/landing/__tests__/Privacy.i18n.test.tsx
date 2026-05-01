import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";

describe("Privacy page — 030 EN/TR/ES i18n", () => {
  it("renders English by default (?lang missing)", () => {
    const { container } = render(<PrivacyPage />);
    const main = container.querySelector("main");
    expect(main?.getAttribute("data-lang")).toBe("en");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Privacy Policy",
    );
    // English-only phrasing of the controller line
    expect(container.textContent).toMatch(/Data Controller/);
  });

  it("renders Turkish when ?lang=tr", () => {
    const { container } = render(
      <PrivacyPage searchParams={{ lang: "tr" }} />,
    );
    expect(container.querySelector("main")?.getAttribute("data-lang")).toBe("tr");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Gizlilik Politikası",
    );
    expect(container.textContent).toMatch(/Veri Sorumlusu/);
  });

  it("renders Spanish when ?lang=es", () => {
    const { container } = render(
      <PrivacyPage searchParams={{ lang: "es" }} />,
    );
    expect(container.querySelector("main")?.getAttribute("data-lang")).toBe("es");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Política de Privacidad",
    );
    expect(container.textContent).toMatch(/Responsable del Tratamiento/);
  });
});
