/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";

import BetaRequestForm from "@/components/BetaRequestForm";

export const metadata: Metadata = {
  title: "Request Beta Access",
  description:
    "Get early access to Automatia ABS — 100+ MCP tools and 6-provider cascade on your own server.",
};

export default function BetaPage() {
  return (
    <main className="container mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Request beta access
      </h1>
      <p className="mt-3 text-sm text-muted-foreground">
        ABS is shipping fast and we want feedback from real teams. Beta is free
        for 30 days; you keep ownership of all data and you can cancel any
        time.
      </p>
      <div className="mt-8">
        <BetaRequestForm />
      </div>
    </main>
  );
}
