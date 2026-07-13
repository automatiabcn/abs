/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q6 PA — pricing page deprecated. The /pricing route now redirects to
// /#contact. This component remains as a thin Pilot/PoC contact CTA so
// any lingering imports keep compiling, but no $/€/lifetime copy is
// rendered. Three legacy plan cards collapsed into a single "Pilot/PoC"
// outreach block.
"use client";

import type { FC } from "react";

import { type Lang } from "@/lib/i18n";

interface PricingPageProps {
  lang?: Lang;
}

const PricingPage: FC<PricingPageProps> = () => {
  return (
    <section
      id="pricing"
      data-testid="pricing-page"
      className="border-t border-border/60 bg-background py-16"
    >
      <div className="container mx-auto px-4 text-center">
        <h2 className="mb-2 text-3xl font-bold tracking-tight">
          Pilot / PoC call
        </h2>
        <p className="mb-8 text-muted-foreground">
          Get in touch to try the system in your own environment.
        </p>
        <a
          href="mailto:support@automatiabcn.com"
          data-testid="pricing-page-cta"
          className="inline-flex h-11 items-center justify-center rounded-md bg-blue-600 px-6 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Get in touch
        </a>
        <p className="mt-6 text-xs text-muted-foreground">
          support@automatiabcn.com · Barcelona
        </p>
      </div>
    </section>
  );
};

export default PricingPage;
