// FOUNDER_FIX_1 / SWEEP — server-component sibling that gives this client
// route a unique <title>. The parent /panel layout still owns the chrome;
// this file only contributes metadata. Do not add UI here.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Sohbet — ABS Panel",
  robots: { index: false, follow: false },
};

export default function ChatLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
