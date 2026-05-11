/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2D ITEM-4 — Tremor AreaChart wrapper for /admin/usage. Extracted
// so the parent UsageClient can `next/dynamic({ssr:false})` it, keeping
// Tremor + Recharts out of the initial /admin/usage chunk.
"use client";

import { AreaChart } from "@tremor/react";

export type UsageTrendPoint = { date: string; "Claude tokens": number };

export default function UsageTrendChart({ data }: { data: UsageTrendPoint[] }) {
  return (
    <AreaChart
      className="h-64"
      data={data}
      index="date"
      categories={["Claude tokens"]}
      colors={["indigo"]}
      showAnimation
      showLegend={false}
      showGridLines={false}
      curveType="monotone"
      yAxisWidth={48}
    />
  );
}
