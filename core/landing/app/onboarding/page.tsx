// T-R04 — onboarding walkthrough route. T-R06 — i18n via ?lang= search param.
import type { Metadata } from "next";

import OnboardingFlow from "@/components/onboarding/OnboardingFlow";
import { type Lang, isLang } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Onboarding — Automatia ABS",
  description:
    "Five-step setup walkthrough: workspace → project → invites → RAG ingest → grounded query.",
  robots: { index: false, follow: false },
};

type SearchParams = { lang?: string };

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const resolved = (await searchParams) ?? {};
  const lang: Lang = isLang(resolved.lang) ? resolved.lang : "en";
  return (
    <main
      data-page="onboarding"
      data-lang={lang}
      style={{
        background: "var(--abs-surface-base)",
        color: "var(--abs-foreground)",
      }}
    >
      <OnboardingFlow lang={lang} />
    </main>
  );
}
