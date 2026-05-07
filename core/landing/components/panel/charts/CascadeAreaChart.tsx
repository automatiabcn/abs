/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 21 / Faz B — Tremor AreaChart wrapper. Extracted into its
// own file so the parent page can `next/dynamic({ssr:false})` the
// chart, keeping Tremor + Recharts out of the initial /panel bundle.
"use client";

import { AreaChart } from "@tremor/react";

export type CascadeAreaPoint = { date: string; Calls: number };

export default function CascadeAreaChart({
  data,
}: {
  data: CascadeAreaPoint[];
}) {
  return (
    <AreaChart
      className="h-64"
      data={data}
      index="date"
      categories={["Calls"]}
      colors={["indigo"]}
      showAnimation
      showLegend={false}
      showGridLines={false}
      curveType="monotone"
      yAxisWidth={40}
    />
  );
}
