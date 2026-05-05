// FOUNDER_FIX_1 / SWEEP — server sibling, metadata-only.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Knowledge Graph — ABS Admin",
  robots: { index: false, follow: false },
};

export default function GraphLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
