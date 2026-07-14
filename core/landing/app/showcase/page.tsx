/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Visual gallery. Renders the OKLCH token palette, ABS-branded icons,
// and the MetricCard / PricingTierCard components for design review.
import type { Metadata } from "next";

import MetricCard from "@/components/showcase/MetricCard";
import PricingTierCard from "@/components/showcase/PricingTierCard";
import {
  AbsLogo,
  AbsCascade,
  AbsRag,
  AbsTenant,
} from "@/components/icons";
export const metadata: Metadata = {
  title: "Showcase — Automatia ABS",
  description: "ABS visual system gallery: OKLCH tokens, brand icons, dashboard + pricing components.",
  robots: { index: false, follow: false },
};

const TOKENS = [
  ["--abs-brand-base", "Brand base"],
  ["--abs-brand-soft", "Brand soft"],
  ["--abs-accent-cyan", "Accent cyan"],
  ["--abs-accent-cyan-soft", "Accent cyan soft"],
  ["--abs-success", "Success"],
  ["--abs-warning", "Warning"],
  ["--abs-danger", "Danger"],
  ["--abs-info", "Info"],
  ["--abs-surface-base", "Surface base"],
  ["--abs-surface-raised", "Surface raised"],
  ["--abs-surface-sunken", "Surface sunken"],
  ["--abs-foreground", "Foreground"],
] as const;

const ICONS = [
  { node: <AbsLogo size={48} />, name: "AbsLogo" },
  { node: <AbsCascade size={48} />, name: "AbsCascade" },
  { node: <AbsRag size={48} />, name: "AbsRag" },
  { node: <AbsTenant size={48} />, name: "AbsTenant" },
] as const;

export default function ShowcasePage() {
  return (
    <main
      className="min-h-screen px-6 py-12"
      style={{ background: "var(--abs-surface-base)", color: "var(--abs-foreground)" }}
      data-testid="showcase-page"
    >
      <div className="mx-auto max-w-6xl">
        <header className="mb-12">
          <h1 className="text-4xl font-bold tracking-tight">ABS visual system</h1>
          <p className="mt-2 text-sm opacity-65">
            Gallery — OKLCH tokens, brand icons, dashboard + pricing components.
          </p>
        </header>

        {/* Tokens */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold">OKLCH tokens (12)</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {TOKENS.map(([token, label]) => (
              <div
                key={token}
                className="overflow-hidden rounded-lg border"
                style={{
                  borderColor: "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
                }}
              >
                <div
                  role="img"
                  aria-label={label}
                  className="h-16"
                  style={{ background: `var(${token})` }}
                />
                <div className="p-3 text-xs">
                  <div className="font-semibold">{label}</div>
                  <code className="opacity-65">{token}</code>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Icons */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold">ABS brand icons (4)</h2>
          <p className="mb-4 text-xs opacity-65">
            Full set pairs with @phosphor-icons/react for general utility icons.
          </p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {ICONS.map((entry) => (
              <div
                key={entry.name}
                className="flex flex-col items-center gap-2 rounded-lg border p-6"
                style={{
                  borderColor: "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
                  color: "var(--abs-brand-base)",
                }}
              >
                {entry.node}
                <code className="text-xs opacity-75" style={{ color: "var(--abs-foreground)" }}>
                  {entry.name}
                </code>
              </div>
            ))}
          </div>
        </section>

        {/* Metric cards */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold">Dashboard metric cards</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="RAG queries (24h)"
              value="12,847"
              trend="up"
              delta="+18%"
              status="ok"
              icon={<AbsRag size={16} />}
              hint="42 tenants active"
            />
            <MetricCard
              label="Cascade routed"
              value="3,420"
              trend="up"
              delta="+820"
              status="ok"
              icon={<AbsCascade size={16} />}
              hint="vs. single-provider baseline"
            />
            <MetricCard
              label="P99 latency"
              value="384ms"
              trend="flat"
              delta="±2%"
              status="warn"
              hint="Budget: 500ms"
            />
            <MetricCard
              label="Cohere quota"
              value="91%"
              trend="up"
              delta="+12%"
              status="danger"
              hint="Approaching daily cap"
            />
          </div>
        </section>

        {/* Pilot/PoC contact options */}
        <section>
          <h2 className="mb-4 text-xl font-semibold">Pilot / PoC options</h2>
          <div className="grid gap-6 md:grid-cols-3">
            <PricingTierCard
              tier="self-host"
              name="PoC"
              price=""
              cadence="installed on your own server"
              badge="Start fast"
              highlight
              features={[
                "Helm chart + documentation",
                "Basic email support",
                "100+ MCP tools included",
                "Runs in your own environment",
              ]}
              cta={
                <a
                  href="mailto:support@automatiabcn.com"
                  className="flex h-10 w-full items-center justify-center rounded-md text-sm font-semibold"
                  style={{
                    background: "var(--abs-brand-base)",
                    color: "#ffffff",
                  }}
                >
                  Get in touch
                </a>
              }
            />
            <PricingTierCard
              tier="maintenance"
              name="Pilot"
              price=""
              cadence="2 weeks of custom integration"
              features={[
                "Connected to your own systems",
                "On-site support",
                "Custom workflow design",
              ]}
              cta={
                <a
                  href="mailto:support@automatiabcn.com"
                  className="flex h-10 w-full items-center justify-center rounded-md border text-sm font-semibold"
                  style={{
                    borderColor: "var(--abs-brand-base)",
                    color: "var(--abs-brand-text)",
                  }}
                >
                  Start a pilot
                </a>
              }
            />
            <PricingTierCard
              tier="managed"
              name="Beta Partner"
              price=""
              cadence="30 days"
              features={[
                "Full access",
                "Feedback partner",
                "Limited spots",
              ]}
              cta={
                <a
                  href="mailto:support@automatiabcn.com"
                  className="flex h-10 w-full items-center justify-center rounded-md border text-sm font-semibold"
                  style={{
                    borderColor: "color-mix(in oklch, var(--abs-foreground) 25%, transparent)",
                    color: "var(--abs-foreground)",
                  }}
                >
                  Apply
                </a>
              }
            />
          </div>
        </section>
      </div>
    </main>
  );
}
