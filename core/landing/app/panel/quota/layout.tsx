// FOUNDER_FIX_1 / SWEEP — server sibling, metadata-only.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Kota — ABS Panel · Automatia ABS",
  robots: { index: false, follow: false },
};

export default function QuotaLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
