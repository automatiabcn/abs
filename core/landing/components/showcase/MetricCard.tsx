/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R03 revise — Dashboard metric card with multi-layer 3D shadow, Framer Motion
// hover-lift, JetBrains Mono number, and data-component selectors.
"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { TrendUp, TrendDown, Minus, type IconWeight } from "@phosphor-icons/react";

type Trend = "up" | "down" | "flat";
type Status = "ok" | "warn" | "danger";

export interface MetricCardProps {
  label: string;
  value: string;
  trend?: Trend;
  delta?: string;
  status?: Status;
  icon?: ReactNode;
  hint?: string;
}

const STATUS_BG: Record<Status, string> = {
  ok: "var(--abs-success)",
  warn: "var(--abs-warning)",
  danger: "var(--abs-danger)",
};

const TREND_ICON: Record<Trend, ReactNode> = {
  up: <TrendUp size={16} weight={"bold" satisfies IconWeight} />,
  down: <TrendDown size={16} weight={"bold" satisfies IconWeight} />,
  flat: <Minus size={16} weight={"bold" satisfies IconWeight} />,
};

const TREND_COLOR: Record<Trend, string> = {
  up: "var(--abs-success)",
  down: "var(--abs-danger)",
  flat: "var(--abs-info)",
};

export default function MetricCard({
  label,
  value,
  trend,
  delta,
  status = "ok",
  icon,
  hint,
}: MetricCardProps) {
  return (
    <motion.article
      data-component="metric-card"
      data-status={status}
      initial={{ opacity: 1, y: 0 }}
      whileHover={{
        y: -2,
        boxShadow: "var(--abs-shadow-hover)",
        transition: { duration: 0.18, ease: "easeOut" },
      }}
      whileFocus={{
        outline: "2px solid var(--abs-accent-cyan)",
        outlineOffset: 2,
      }}
      className="relative flex flex-col rounded-xl border p-5"
      style={{
        background: "var(--abs-surface-raised)",
        color: "var(--abs-foreground)",
        borderColor:
          "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
        boxShadow: "var(--abs-shadow-rest)",
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wide opacity-70">
          {icon}
          <span>{label}</span>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[11px] font-bold uppercase"
          style={{
            background: STATUS_BG[status],
            color: "var(--abs-surface-base)",
          }}
        >
          {status}
        </span>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="num-mono text-3xl font-bold">{value}</span>
        {trend && delta ? (
          <span
            className="flex items-center gap-1 text-sm font-medium"
            style={{ color: TREND_COLOR[trend] }}
          >
            {TREND_ICON[trend]}
            <span className="num-mono">{delta}</span>
          </span>
        ) : null}
      </div>
      {hint ? (
        <p className="mt-3 text-xs opacity-60">{hint}</p>
      ) : null}
    </motion.article>
  );
}
