/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";

import { type Lang, isLang, t } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "GDPR-compliant privacy policy for the ABS self-host orchestrator. Data controller: Automatia BCN.",
};

type SearchParams = { lang?: string };

export default async function PrivacyPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const resolved = (await searchParams) ?? {};
  const requested = resolved.lang;
  const lang: Lang = isLang(requested) ? requested : "en";
  const tr = (k: string) => t(k, lang);

  return (
    <main className="container mx-auto max-w-3xl px-4 py-16" data-lang={lang}>
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        {tr("privacy.title")}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {tr("privacy.lastUpdated")}
      </p>

      <div className="prose prose-neutral mt-8 space-y-6 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">1. {tr("privacy.dataController")}</h2>
          <p>{tr("privacy.dataController.body")}</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">
            2. {tr("privacy.dataCollected.title")}
          </h2>
          <ul className="list-disc pl-6">
            <li>{tr("privacy.dataCollected.email")}</li>
            <li>{tr("privacy.dataCollected.payment")}</li>
            <li>{tr("privacy.dataCollected.license")}</li>
            <li>{tr("privacy.dataCollected.logs")}</li>
          </ul>
          <p>{tr("privacy.dataCollected.body")}</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">3. {tr("privacy.purpose.title")}</h2>
          <p>{tr("privacy.purpose.body")}</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. {tr("privacy.processors.title")}</h2>
          <ul className="list-disc pl-6">
            <li>{tr("privacy.processors.stripe")}</li>
            <li>{tr("privacy.processors.anthropic")}</li>
            <li>{tr("privacy.processors.hetzner")}</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">5. {tr("privacy.retention.title")}</h2>
          <p>{tr("privacy.retention.body")}</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">6. {tr("privacy.rights.title")}</h2>
          <ul className="list-disc pl-6">
            <li>{tr("privacy.rights.access")}</li>
            <li>{tr("privacy.rights.portability")}</li>
            <li>{tr("privacy.rights.objection")}</li>
            <li>
              {tr("privacy.rights.complain")} (
              <a
                href="https://www.aepd.es"
                className="underline"
                rel="noreferrer noopener"
                target="_blank"
              >
                aepd.es
              </a>
              )
            </li>
          </ul>
        </section>

        <section data-testid="gdpr-rights-exercise">
          <h2 className="text-lg font-semibold">
            6a. {tr("privacy.exercise.title")}
          </h2>
          <p>{tr("privacy.exercise.intro")}</p>
          <ul className="list-disc pl-6">
            <li>
              <strong>{tr("privacy.exercise.export")}</strong>
            </li>
            <li>
              <strong>{tr("privacy.exercise.delete")}</strong>
            </li>
            <li>
              <strong>{tr("privacy.exercise.consent")}</strong>
            </li>
            <li>
              <strong>{tr("privacy.exercise.audit")}</strong>
            </li>
          </ul>
        </section>

        <section data-testid="gdpr-subprocessors-link">
          <h2 className="text-lg font-semibold">
            6b. {tr("privacy.subprocessors.title")}
          </h2>
          <p>
            {tr("privacy.subprocessors.body")}{" "}
            <a
              href="https://github.com/automatiabcn/abs-server-product/blob/main/docs/legal/subprocessors.md"
              className="underline"
              rel="noreferrer noopener"
              target="_blank"
            >
              docs/legal/subprocessors.md
            </a>{" "}
            ·{" "}
            <a
              href="https://github.com/automatiabcn/abs-server-product/blob/main/docs/legal/dpa-template.md"
              className="underline"
              rel="noreferrer noopener"
              target="_blank"
            >
              docs/legal/dpa-template.md
            </a>
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">7. {tr("privacy.contact.title")}</h2>
          <p>
            <a href="mailto:privacy@automatiabcn.com" className="underline">
              privacy@automatiabcn.com
            </a>{" "}
            — {tr("privacy.contact.body")}
          </p>
        </section>
      </div>
    </main>
  );
}
