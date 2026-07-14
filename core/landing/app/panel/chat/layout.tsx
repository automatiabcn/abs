/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// SWEEP — server-component sibling that gives this client
// route a unique <title>. The parent /panel layout still owns the chrome;
// this file only contributes metadata. Do not add UI here.
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Chat — ABS Panel",
  robots: { index: false, follow: false },
};

export default function ChatLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
