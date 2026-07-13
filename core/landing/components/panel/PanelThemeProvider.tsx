/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q7 Phase C — next-themes wrapper for /panel + /admin.
"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

interface PanelThemeProviderProps {
  children: ReactNode;
}

// The panel opened dark for everyone, which suited the people who built it and
// nobody who buys it. Following the operating system is the honest default: a
// console someone runs a business from should look like the rest of their
// working day, and light is now designed to the same standard rather than being
// an inverted afterthought. An explicit toggle still wins over both.
export function PanelThemeProvider({ children }: PanelThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
