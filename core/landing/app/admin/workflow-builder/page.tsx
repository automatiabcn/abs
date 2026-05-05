import type { Metadata } from "next";
import { headers } from "next/headers";

import WorkflowChatPanel from "@/components/WorkflowChatPanel";
import { SAMPLE_WORKFLOW } from "@/lib/workflow";

export const metadata: Metadata = {
  title: "Workflow Builder — ABS Admin",
  robots: { index: false, follow: false },
};

export default async function Page() {
  const h = await headers();
  const isAdmin = h.get("x-abs-role") === "admin";
  return (
    <main className="mx-auto max-w-7xl px-6 py-12">
      <h1 className="text-3xl font-semibold text-zinc-900 dark:text-zinc-50">
        Workflow Builder
      </h1>
      <p className="mt-2 mb-8 max-w-2xl text-zinc-600 dark:text-zinc-300">
        Doğal dilde anlat — ABS, tenant policy kontrolleri ve human-in-the-loop
        kapıları gömülü n8n-uyumlu workflow üretir.
      </p>
      <WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={isAdmin} />
    </main>
  );
}
