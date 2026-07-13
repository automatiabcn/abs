/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q7 Phase C — premium dark/light toggle (next-themes powered).
// Q8 / MT3 fix — defer the aria-label + icon swap until after mount so
// SSR (theme=undefined) doesn't disagree with CSR (theme=resolvedTheme).
"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme, resolvedTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Stable shell during hydration — same DOM as the post-mount render
    // minus theme-dependent attributes. Avoids the aria-label mismatch
    // captured in UX_BUGS_20260501.md MT3.
    return (
      <Button
        variant="ghost"
        size="icon"
        aria-label="Toggle theme"
        data-test="theme-toggle"
        suppressHydrationWarning
      >
        <Sun className="h-4 w-4" />
      </Button>
    );
  }

  const current = theme === "system" ? resolvedTheme : theme;
  const next = current === "dark" ? "light" : "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      aria-label={
        next === "dark" ? "Switch to dark theme" : "Switch to light theme"
      }
      data-test="theme-toggle"
    >
      <Sun className="h-4 w-4 dark:hidden" />
      <Moon className="hidden h-4 w-4 dark:block" />
    </Button>
  );
}
