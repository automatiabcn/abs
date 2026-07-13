"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import * as React from "react";

import { BILLING_DISABLED_TITLE, BILLING_ENABLED } from "@/lib/billing-flag";

export type CheckoutTier = "self-host" | "maintenance" | "team-5" | "team-10";

interface CheckoutButtonProps {
  tier: CheckoutTier;
  children: React.ReactNode;
  variant?: "primary" | "secondary";
  className?: string;
}

export default function CheckoutButton({
  tier,
  children,
  variant = "primary",
  className = "",
}: CheckoutButtonProps) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleClick = async () => {
    // T-R03 fix #1 — honour the global billing kill-switch.
    if (!BILLING_ENABLED) {
      setError(BILLING_DISABLED_TITLE);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });

      if (!res.ok) {
        const errData = (await res.json().catch(() => ({}))) as {
          error?: string;
        };
        throw new Error(errData.error ?? "Could not start checkout");
      }

      const data = (await res.json()) as { url?: string };
      if (data.url) {
        window.location.href = data.url;
      } else {
        throw new Error("No Stripe URL returned");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  };

  const baseClasses =
    "inline-flex h-11 items-center justify-center rounded-md px-6 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none";

  const variantClasses =
    variant === "secondary"
      ? "border border-input bg-transparent text-foreground hover:bg-muted"
      : "bg-primary text-primary-foreground hover:opacity-90";

  return (
    <>
      <button
        type="button"
        data-test="checkout-button"
        data-tier={tier}
        onClick={handleClick}
        disabled={loading || !BILLING_ENABLED}
        aria-busy={loading}
        aria-disabled={!BILLING_ENABLED}
        title={BILLING_ENABLED ? undefined : BILLING_DISABLED_TITLE}
        className={`${baseClasses} ${variantClasses} ${className}`}
      >
        {loading ? "Processing…" : children}
      </button>
      {error && (
        <p role="alert" aria-live="polite" className="mt-2 text-sm text-red-500">
          {error}
        </p>
      )}
    </>
  );
}
