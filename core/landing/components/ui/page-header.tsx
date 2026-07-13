/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Every panel page opened with its own hand-rolled title block: a heading, a
// line of description, sometimes an icon, sometimes an action button, each at a
// slightly different size and spacing. This is that block, once.
//
// `description` earns its place — it is where a page says what it is for in
// plain language, which is most of what the naming work was about.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-wrap items-start justify-between gap-4 pb-6",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl text-foreground">{title}</h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
