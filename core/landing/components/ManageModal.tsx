"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import * as React from "react";

import { BILLING_ENABLED } from "@/lib/billing-flag";

interface ManageModalProps {
  /**
   * Override the link text. Defaults to "Manage".
   */
  linkLabel?: string;
}

const PORTAL_ENDPOINT = "/api/billing-portal";

const ManageModal: React.FC<ManageModalProps> = ({ linkLabel = "Manage" }) => {
  const [open, setOpen] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const reset = () => {
    setEmail("");
    setError(null);
    setLoading(false);
  };

  const onClose = () => {
    if (loading) return;
    setOpen(false);
    reset();
  };

  // Escape closes the modal (unless a request is in flight), matching the
  // backdrop-click and Cancel paths a keyboard user can't otherwise reach.
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) {
        setOpen(false);
        reset();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, loading]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    // A stuck endpoint must not strand the button on "Opening…" — abort after
    // 15s and surface an error the person can retry, rather than spin forever.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15_000);
    try {
      const res = await fetch(PORTAL_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_email: email }),
        signal: ctrl.signal,
      });
      if (res.status === 404) {
        throw new Error("No license found for that email. Check the address, or buy a license first.");
      }
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(data.error ?? "Could not open the billing portal. Try again.");
      }
      const data = (await res.json()) as { portal_url?: string };
      if (data.portal_url) {
        window.location.href = data.portal_url;
        return; // keep the modal open, still showing the loading state
      }
      throw new Error("Could not open the billing portal. Try again.");
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "AbortError"
          ? "The billing portal is taking too long. Try again."
          : err instanceof Error
            ? err.message
            : "Something went wrong. Try again.";
      setError(msg);
      setLoading(false);
    } finally {
      clearTimeout(timer);
    }
  };

  // Billing kill-switch hides the entry point entirely.
  if (!BILLING_ENABLED) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-sm font-medium text-foreground hover:text-primary"
        aria-haspopup="dialog"
      >
        {linkLabel}
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="manage-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={onClose}
        >
          <div
            className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="manage-modal-title"
              className="text-lg font-semibold"
            >
              Manage your subscription
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Enter the email on your license and we&apos;ll take you to the
              Stripe billing portal.
            </p>

            <form onSubmit={onSubmit} className="mt-4 space-y-3">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                aria-label="Email"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                disabled={loading}
              />
              {error && (
                <p role="alert" className="text-sm text-red-500">
                  {error}
                </p>
              )}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={loading}
                  className="text-sm text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !email}
                  aria-busy={loading}
                  className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? "Opening…" : "Open billing portal"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};

export default ManageModal;
