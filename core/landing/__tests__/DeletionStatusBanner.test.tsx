// DeletionStatusBanner renders the three states
// (none / scheduled / purged) and the cancel button when scheduled.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DeletionStatusBanner from "@/components/DeletionStatusBanner";

describe("DeletionStatusBanner", () => {
  it("renders the 'no pending deletion' state", () => {
    render(<DeletionStatusBanner data={{ status: "none" }} lang="en" />);
    expect(
      screen.getByText("No deletion request is currently pending for this account."),
    ).toBeInTheDocument();
  });

  it("renders the scheduled state with countdown + cancel button", async () => {
    const onCancel = vi.fn();
    render(
      <DeletionStatusBanner
        data={{
          status: "scheduled",
          scheduled_delete_at: "2026-06-13T00:00:00Z",
          days_remaining: 30,
        }}
        lang="en"
        onCancel={onCancel}
      />,
    );
    expect(
      screen.getByRole("alert", { name: /scheduled for deletion/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/30 days left to cancel/i)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /cancel deletion/i }),
    );
    expect(onCancel).toHaveBeenCalled();
  });

  it("renders the purged state with the purge date", () => {
    render(
      <DeletionStatusBanner
        data={{ status: "purged", purged_at: "2026-04-30T00:00:00Z" }}
        lang="en"
      />,
    );
    expect(screen.getByText(/Account already purged/i)).toBeInTheDocument();
    expect(
      screen.getByText(/personal data on this account was purged on/i),
    ).toBeInTheDocument();
  });

  it("honours the Turkish locale", () => {
    render(<DeletionStatusBanner data={{ status: "none" }} lang="tr" />);
    expect(
      screen.getByText("Bu hesap için bekleyen bir silme talebi yok."),
    ).toBeInTheDocument();
  });
});
