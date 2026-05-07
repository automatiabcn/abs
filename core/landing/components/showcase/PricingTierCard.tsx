/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R03 revise — Glassmorphism pricing tier card with Framer Motion hover lift,
// brand-gradient border on highlight, and cyan focus ring.
"use client";

import { CheckCircle, type IconWeight } from "@phosphor-icons/react";
import { motion } from "framer-motion";
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

import { BILLING_DISABLED_TITLE, BILLING_ENABLED } from "@/lib/billing-flag";

export interface PricingTierCardProps {
  name: string;
  price: string;
  cadence: string;
  features: string[];
  cta: ReactNode;
  highlight?: boolean;
  badge?: string;
  /** Stable identifier surfaced as `data-tier` for analytics + Playwright. */
  tier?: "self-host" | "maintenance" | "managed";
}

// T-R03 fix #1 — when billing is gated off, every CTA on every PricingTierCard
// is forced into a disabled visual + cannot be activated. We inject this at
// component level so callers passing custom JSX still get gated.
function gateCta(cta: ReactNode): ReactNode {
  if (BILLING_ENABLED) return cta;
  if (!isValidElement(cta)) return cta;
  const element = cta as ReactElement<Record<string, unknown>>;
  const existingClassName =
    typeof element.props.className === "string" ? element.props.className : "";
  return cloneElement(element, {
    disabled: true,
    "aria-disabled": "true",
    title: BILLING_DISABLED_TITLE,
    onClick: undefined,
    className:
      `${existingClassName} opacity-60 cursor-not-allowed pointer-events-none`.trim(),
  });
}

export default function PricingTierCard({
  name,
  price,
  cadence,
  features,
  cta,
  highlight,
  badge,
  tier,
}: PricingTierCardProps) {
  return (
    <motion.article
      data-component="pricing-tier"
      data-tier={tier}
      data-highlight={highlight ? "true" : "false"}
      initial={{ opacity: 1, y: 0 }}
      whileHover={{
        y: -4,
        scale: 1.02,
        transition: { duration: 0.22, ease: "easeOut" },
      }}
      tabIndex={0}
      className="group relative flex flex-col rounded-2xl p-[1.5px] focus-visible:outline-none"
      style={{
        background: highlight
          ? "linear-gradient(135deg, var(--abs-brand-base) 0%, var(--abs-accent-cyan) 100%)"
          : "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
        boxShadow: highlight ? "var(--abs-shadow-rest)" : "none",
      }}
    >
      <div
        className="relative flex h-full flex-col rounded-[14px] p-6"
        style={{
          background: highlight ? "var(--abs-glass-bg-soft)" : "var(--abs-glass-bg)",
          backdropFilter: "blur(12px) saturate(140%)",
          WebkitBackdropFilter: "blur(12px) saturate(140%)",
          color: "var(--abs-foreground)",
        }}
      >
        {badge ? (
          <span
            className="absolute -top-3 right-4 rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wide"
            style={{
              background: "var(--abs-brand-base)",
              color: "var(--abs-surface-base)",
              boxShadow:
                "0 4px 12px color-mix(in oklch, var(--abs-brand-base) 35%, transparent)",
            }}
          >
            {badge}
          </span>
        ) : null}

        <header>
          <h3 className="text-lg font-semibold">{name}</h3>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="num-mono text-3xl font-bold">{price}</span>
            <span className="text-sm opacity-65">{cadence}</span>
          </div>
        </header>

        <ul className="mt-5 flex flex-col gap-2 text-sm">
          {features.map((feature) => (
            <li key={feature} className="flex items-start gap-2">
              <CheckCircle
                size={18}
                weight={"fill" satisfies IconWeight}
                style={{ color: "var(--abs-success)", flexShrink: 0 }}
              />
              <span>{feature}</span>
            </li>
          ))}
        </ul>

        <div
          className="mt-6"
          data-billing-gated={BILLING_ENABLED ? "false" : "true"}
        >
          {gateCta(cta)}
        </div>
      </div>
    </motion.article>
  );
}
