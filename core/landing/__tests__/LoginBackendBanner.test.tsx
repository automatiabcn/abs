/**
 * Fail-closed landing SSR.
 *
 * The /admin/* and /panel/* SSR layouts redirect to
 * /login?reason=backend-unreachable when the backend /healthz probe fails.
 * The login page picks that query param up and shows a banner.
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

describe("LoginPage — backend-unreachable banner", () => {
  it("shows the banner when reason=backend-unreachable", () => {
    mockSearchParams.mockImplementation((key: string) =>
      key === "reason" ? "backend-unreachable" : null,
    );
    render(<LoginPage />);
    const banner = screen.getByTestId("backend-unreachable-banner");
    expect(banner.textContent).toContain("The backend is unreachable right now");
    expect(banner.textContent).toContain("Please try again in a few minutes");
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
