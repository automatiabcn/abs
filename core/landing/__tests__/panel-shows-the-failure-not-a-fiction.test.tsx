/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What the audit and users pages do when the server did not answer.
//
// This lives here rather than in the scenario suite for a reason worth stating:
// both pages fetch server-side, inside Next, so a Playwright `page.route` mock
// never sees the request — the browser is not the one making it. A scenario test
// that "proves" the failure state by blocking a request the page never sends
// passes without once rendering the thing it claims to check. (It did. That is
// how this file came to exist.)
//
// The prop is the honest seam: `loadError` is exactly what the server component
// passes down when its own fetch failed, so setting it here drives the same code
// a customer hits.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import AuditClient from "@/app/admin/audit/AuditClient";
import UsageClient from "@/app/admin/usage/UsageClient";
import UsersClient from "@/app/admin/users/UsersClient";

// The islands refetch on mount. Nothing is listening, and nothing should be: a
// failed refetch on top of a failed server render is exactly the case under test.
vi.stubGlobal(
  "fetch",
  vi.fn(() => Promise.reject(new Error("backend is down"))),
);

// The app marks test hooks with `data-test`, not `data-testid`, so testing
// library's *ByTestId helpers quietly find nothing. Ask for what is actually there.
const at = (root: HTMLElement, name: string) =>
  root.querySelector(`[data-test="${name}"]`);
const allAt = (root: HTMLElement, name: string) =>
  root.querySelectorAll(`[data-test="${name}"]`);

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("the audit page, when the log could not be read", () => {
  it("says so, shows no entries, and invents none", async () => {
    const { container } = renderWithQuery(
      <AuditClient initialEntries={[]} loadError="The server answered 503." />,
    );

    await waitFor(() => expect(at(container, "audit-load-error")).not.toBeNull());
    expect(container.textContent).toMatch(/could not be read/i);
    expect(allAt(container, "audit-row")).toHaveLength(0);

    // The fabricated fixture's fingerprints: a demo-tenant actor, and rows
    // carrying hmac strings — both of which used to render right here, with
    // nothing on screen to say they were samples.
    expect(container.textContent).not.toMatch(/demo-acme/);
    expect(container.textContent).not.toMatch(/hmac:/);
  });

  it("will not export evidence it never read", async () => {
    const { container } = renderWithQuery(
      <AuditClient initialEntries={[]} loadError="The server answered 503." />,
    );
    await waitFor(() => expect(at(container, "audit-load-error")).not.toBeNull());

    // The CSV button sits under copy offering these rows as GDPR Article 15 /
    // SOC 2 evidence. A file reaching an auditor from a page that read nothing
    // is the worst thing this page could do.
    expect(at(container, "audit-export")).toBeDisabled();
  });

  it("still shows real entries when there are real entries", async () => {
    // The other half of the contract. Refusing to invent must not decay into
    // refusing to show — a fix that blanks the page on success is not a fix.
    const { container } = renderWithQuery(
      <AuditClient
        loadError={null}
        initialEntries={[
          {
            id: 1,
            ts: new Date().toISOString(),
            actor: "real@customer.example",
            action: "auth.login",
            detail: "signed in",
          },
        ]}
      />,
    );

    await waitFor(() => expect(allAt(container, "audit-row")).toHaveLength(1));
    expect(container.textContent).toMatch(/auth\.login/);
    expect(at(container, "audit-load-error")).toBeNull();
    expect(at(container, "audit-export")).not.toBeDisabled();
  });
});

describe("the chain check does not congratulate itself on an empty log", () => {
  function respondWithChain(body: Record<string, unknown>) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        String(url).includes("verify-chain")
          ? Promise.resolve(
              new Response(JSON.stringify(body), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              }),
            )
          : Promise.reject(new Error("not under test")),
      ),
    );
  }

  it("says nothing was recorded, rather than 'Log intact'", async () => {
    // The API is right that an empty chain is not tampered with. The button was
    // wrong to render that as reassurance: "Log intact" over zero entries is a
    // green tick on no work, and it is precisely what this button displayed for
    // months while the recorder wrote to a logger with no handler.
    respondWithChain({ ok: true, total_entries: 0, tampered_entry_id: null });

    const { container } = renderWithQuery(
      <AuditClient initialEntries={[]} loadError={null} />,
    );
    fireEvent.click(at(container, "audit-verify-chain")!);

    await waitFor(() =>
      expect(container.textContent).toMatch(/nothing recorded yet/i),
    );
    expect(container.textContent).not.toMatch(/intact/i);
  });

  it("says intact only when it has actually checked something, and says how much", async () => {
    respondWithChain({ ok: true, total_entries: 412, tampered_entry_id: null });

    const { container } = renderWithQuery(
      <AuditClient initialEntries={[]} loadError={null} />,
    );
    fireEvent.click(at(container, "audit-verify-chain")!);

    await waitFor(() => expect(container.textContent).toMatch(/Log intact/i));
    expect(container.textContent).toMatch(/412 entries checked/i);
  });

  it("says so, loudly, when the chain is broken", async () => {
    // If this ever stops being reachable, the chain is decoration.
    respondWithChain({ ok: false, total_entries: 9, tampered_entry_id: 7 });

    const { container } = renderWithQuery(
      <AuditClient initialEntries={[]} loadError={null} />,
    );
    fireEvent.click(at(container, "audit-verify-chain")!);

    await waitFor(() =>
      expect(container.textContent).toMatch(/tampered with/i),
    );
    expect(container.textContent).toMatch(/#7/);
  });
});

describe("the users page, when the roster could not be read", () => {
  it("lists nobody, and says why", async () => {
    const { container } = renderWithQuery(
      <UsersClient initialUsers={[]} loadError="The server answered 503." />,
    );

    await waitFor(() => expect(at(container, "users-load-error")).not.toBeNull());
    expect(allAt(container, "user-row")).toHaveLength(0);
    // An admin who saw this name on their own server went looking for an account
    // that never existed.
    expect(container.textContent).not.toMatch(/demo-acme/);
  });

  it("still shows the real roster", async () => {
    const { container } = renderWithQuery(
      <UsersClient
        loadError={null}
        initialUsers={[
          {
            id: 1,
            email: "real@customer.example",
            role: "admin",
            status: "active",
            created_at: new Date().toISOString(),
          },
        ]}
      />,
    );

    await waitFor(() =>
      expect(container.textContent).toMatch(/real@customer\.example/),
    );
    expect(at(container, "users-load-error")).toBeNull();
  });
});

describe("the usage page, when the numbers could not be read", () => {
  it("does not confirm the product's own cost claim out of thin air", async () => {
    // The fallback used to pass `free_path.pct_24h = 1` and a 1,000,000-token
    // Claude budget nobody set, which the page renders as "100.0 % served free"
    // the exact claim the customer opened this page to verify.
    const { container } = renderWithQuery(
      <UsageClient initial={null} loadError="The server answered 503." />,
    );

    await waitFor(() => expect(at(container, "usage-load-error")).not.toBeNull());
    expect(container.textContent).not.toMatch(/100\.0 %/);
    expect(container.textContent).not.toMatch(/1,000,000/);
  });
});
