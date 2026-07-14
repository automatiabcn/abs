/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Onboarding walkthrough route. i18n via the ?lang= search param.
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
