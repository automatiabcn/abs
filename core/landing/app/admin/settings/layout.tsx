// FOUNDER_FIX_1 / SWEEP — server sibling, metadata-only.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Ayarlar — ABS Admin · Automatia ABS",
  robots: { index: false, follow: false },
};

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
