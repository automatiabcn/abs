import { headers } from "next/headers";

import Footer from "@/components/Footer";
import WorkflowChatPanel from "@/components/WorkflowChatPanel";
import { SAMPLE_WORKFLOW } from "@/lib/workflow";

export const metadata = {
  title: "NL Workflow Builder — ABS Admin",
  robots: { index: false },
};

export default async function Page() {
  const h = await headers();
  const isAdmin = h.get("x-abs-role") === "admin";
  return (
    <main className="mx-auto max-w-7xl px-6 py-12">
      <h1 className="text-3xl font-semibold text-zinc-900 dark:text-zinc-50">
        NL Workflow Builder
      </h1>
      <p className="mt-2 mb-8 max-w-2xl text-zinc-600 dark:text-zinc-300">
        Describe what you want in plain language. ABS synthesises an
        n8n-compatible workflow with tenant policy checks and human-in-the-loop
        gates baked in.
      </p>
      <WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={isAdmin} />
      <div className="mt-16">
        <Footer />
      </div>
    </main>
  );
}
