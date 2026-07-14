/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Premium animated metric card.
"use client";

import { motion } from "framer-motion";
import { type LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type DeltaType = "increase" | "decrease" | "neutral";

interface StatCardProps {
  title: string;
  value: string | number;
  delta?: string;
  deltaType?: DeltaType;
  hint?: string;
  icon?: LucideIcon;
  delay?: number;
}

const DELTA_STYLE: Record<DeltaType, string> = {
  increase: "text-emerald-500 dark:text-emerald-400",
  decrease: "text-rose-500 dark:text-rose-400",
  neutral: "text-muted-foreground",
};

export function StatCard({
  title,
  value,
  delta,
  deltaType = "neutral",
  hint,
  icon: Icon,
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      <Card
        data-test="stat-card"
        className="overflow-hidden border-border/60 bg-card/60 backdrop-blur"
      >
        <CardContent className="flex items-start justify-between p-6">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {title}
            </span>
            <span className="font-mono text-3xl font-semibold leading-tight text-foreground">
              {value}
            </span>
            {(delta || hint) && (
              <span
                className={cn(
                  "mt-1 text-xs",
                  delta ? DELTA_STYLE[deltaType] : "text-muted-foreground",
                )}
              >
                {delta ?? hint}
                {delta && hint ? (
                  <span className="ml-1 text-muted-foreground">{hint}</span>
                ) : null}
              </span>
            )}
          </div>
          {Icon && (
            <div className="rounded-md border border-border/40 bg-background/40 p-2 text-muted-foreground">
              <Icon className="h-4 w-4" />
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
