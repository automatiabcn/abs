/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// MT7 + cross-phase — reusable empty state for panel/admin pages.
// Drops the bare "No X yet." string in favour of an icon + title +
// description + primary CTA pattern.
"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  ctaLabel?: string;
  onCta?: () => void;
  secondary?: ReactNode;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  ctaLabel,
  onCta,
  secondary,
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      data-test="empty-state"
      className="mx-auto flex max-w-md flex-col items-center justify-center gap-3 px-6 py-12 text-center"
    >
      {/* bg-primary-soft, not bg-primary/10: colours resolve through var() now,
          and Tailwind 3 cannot re-compose an alpha onto one — the opacity
          modifier silently produced no background at all. */}
      <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-primary-soft text-primary">
        <Icon className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {description && (
        <p className="text-sm text-muted-foreground">{description}</p>
      )}
      {ctaLabel && (
        <Button type="button" onClick={onCta} className="mt-2">
          {ctaLabel}
        </Button>
      )}
      {secondary && <div className="mt-2 text-xs text-muted-foreground">{secondary}</div>}
    </motion.div>
  );
}
