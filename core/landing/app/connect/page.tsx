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
