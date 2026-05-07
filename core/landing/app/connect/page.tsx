/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";

import ConnectPanel from "@/components/ConnectPanel";

export const metadata: Metadata = {
  title: "Connected Services — Automatia ABS",
  description:
    "Manage your smart-link integrations: GitHub, Slack, OpenAI, Anthropic, Cohere, Groq, Gemini.",
};

export default function ConnectPage() {
  return (
    <main className="min-h-screen">
      <ConnectPanel />
    </main>
  );
}
