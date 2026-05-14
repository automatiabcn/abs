/**
 * Sprint 2N FAZ B — UAT-009 fail-closed landing SSR (P0 #2M-025).
 *
 * /admin/* ve /panel/* SSR layout'ları backend /healthz probe fail edince
 * /login?reason=backend-unreachable'a redirect ediyor. Login sayfası bu
 * query param'ı yakalayıp Türkçe banner gösteriyor.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

const mockSearchParams = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParams(key),
  }),
}));

describe("LoginPage — backend-unreachable banner (P0 #2M-025)", () => {
  it("shows the Türkçe banner when reason=backend-unreachable", () => {
    mockSearchParams.mockImplementation((key: string) =>
      key === "reason" ? "backend-unreachable" : null,
    );
    render(<LoginPage />);
    const banner = screen.getByTestId("backend-unreachable-banner");
    expect(banner.textContent).toContain("Backend şu an erişilemez");
    expect(banner.textContent).toContain("Lütfen birkaç dakika sonra tekrar deneyin");
  });

  it("hides the banner without reason param", () => {
    mockSearchParams.mockImplementation(() => null);
    render(<LoginPage />);
    const banner = screen.queryByTestId("backend-unreachable-banner");
    expect(banner).toBeNull();
  });

  it("hides the banner for unrelated reason values", () => {
    mockSearchParams.mockImplementation((key: string) =>
      key === "reason" ? "session-expired" : null,
    );
    render(<LoginPage />);
    const banner = screen.queryByTestId("backend-unreachable-banner");
    expect(banner).toBeNull();
  });
});
