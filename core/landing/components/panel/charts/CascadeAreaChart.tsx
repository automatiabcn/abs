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
