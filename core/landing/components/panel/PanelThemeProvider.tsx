// Q7 Phase C — next-themes wrapper for /panel + /admin.
"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

interface PanelThemeProviderProps {
  children: ReactNode;
}

export function PanelThemeProvider({ children }: PanelThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
