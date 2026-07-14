/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import Link from "next/link";
import type { FC } from "react";

import HeroVisual from "./HeroVisual";

interface HeroCta {
  text: string;
  href: string;
}

export interface HeroProps {
  title: string;
  subtitle: string;
  primaryCta: HeroCta;
  secondaryCta: HeroCta;
}

// The visual used to be `absolute inset-0` behind the whole hero, so the scene's
// centre — the orb — landed on the headline: 600 × 300 pixels of overlap,
// measured in the browser, with the sub-heading reading straight through it. It
// now lives in the grid's second column and cannot reach the type at all.
//
// The two background layers went with it. They were painted in `purple-500` and
// rgba(30, 87, 172) — the retired Automatia blue — neither of which is a colour
// this product still uses. What is left is one wash of the brand token, well
// away from the text.
const Hero: FC<HeroProps> = ({ title, subtitle, primaryCta, secondaryCta }) => (
  <section
    aria-labelledby="hero-title"
    className="relative overflow-hidden min-h-[640px]"
  >
    <div
      aria-hidden="true"
      className="absolute inset-0 -z-20 bg-[radial-gradient(900px_420px_at_88%_20%,rgb(var(--abs-brand-rgb)/0.09),transparent_62%)]"
    />

    <div className="container relative mx-auto grid items-center gap-12 px-4 py-24 sm:py-32 lg:grid-cols-[1.05fr_0.95fr]">
      <div className="max-w-2xl">
        <h1
          id="hero-title"
          className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl"
        >
          {title}
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-muted-foreground sm:text-xl">
          {subtitle}
        </p>
        <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row">
          <Link
            href={primaryCta.href}
            className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {primaryCta.text}
          </Link>
          <Link
            href={secondaryCta.href}
            className="inline-flex h-11 items-center justify-center rounded-md border border-input bg-transparent px-8 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {secondaryCta.text}
          </Link>
        </div>

        {/* The counts the headline used to carry. Each one is a fact the product
            can be held to, not a claim. */}
        <dl className="mt-10 flex flex-wrap gap-x-8 gap-y-4">
          {[
            { value: "100+", label: "MCP tools" },
            { value: "6", label: "providers, cascaded" },
            { value: "0", label: "data leaves your server" },
          ].map((fact) => (
            <div key={fact.label} className="flex flex-col">
              <dt className="sr-only">{fact.label}</dt>
              <dd className="font-mono text-lg tabular-nums text-foreground">
                {fact.value}
              </dd>
              <span className="text-xs text-muted-foreground">{fact.label}</span>
            </div>
          ))}
        </dl>
      </div>

      {/* 3D scene on desktop / static SVG on mobile + reduced-motion */}
      <div className="flex justify-center lg:justify-end">
        <HeroVisual />
      </div>
    </div>
  </section>
);

export default Hero;
