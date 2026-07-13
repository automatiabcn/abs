/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Terms of service for the Automatia ABS self-host orchestrator. License, payment, liability, termination.",
};

export default function TermsPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Terms of Service
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Last updated: 27 April 2026.
      </p>

      <div className="prose prose-neutral mt-8 space-y-6 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">1. Parties</h2>
          <p>
            This agreement is entered into between <strong>Automatia BCN</strong>{" "}
            (Barcelona, Spain — hereinafter the &ldquo;Provider&rdquo;) and the
            customer who purchases or uses an Automatia ABS license (the
            &ldquo;User&rdquo;). You must be over 18 to use the service.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">2. Scope of the License</h2>
          <p>
            In exchange for the Self-Host Lifetime payment, the Provider grants
            the User the right to run the ABS software on the User&apos;s own
            servers. The license is{" "}
            <strong>personal / specific to one organization</strong>; it may not
            be transferred or resold to third parties. Team packages carry a
            concurrent-use limit tied to the number of seats.
          </p>
          <p>
            There is no additional commercial restriction on the open-source core
            (Apache 2.0); the closed premium add-ons (advanced RAG, team panel)
            are subject to the license terms.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">3. Payment and Invoicing</h2>
          <p>
            All payments are processed through Stripe Payments Europe Ltd. Billed
            amounts exclude VAT; for B2B purchases inside the EU, the reverse
            charge may apply once the VAT number is validated through VIES.
            Invoices are emailed within 7 days of payment confirmation.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. Refund Policy</h2>
          <p>
            You have an unconditional right to a refund{" "}
            <strong>within 14 days</strong> of the purchase date. The key of a
            refunded license is marked <code>revoked_at</code> and deactivated.
            See the <a href="/refund" className="underline">Refund Policy</a> page
            for details.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">5. Prohibited Uses</h2>
          <ul className="list-disc pl-6">
            <li>Reverse-engineering the software to extract the premium add-ons.</li>
            <li>Distributing the license key to more than one organization.</li>
            <li>
              Generating illegal content through ABS, or committing an
              information-security breach with it.
            </li>
            <li>Filing a fraudulent chargeback with Stripe.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">6. Service Level (SLA)</h2>
          <p>
            In Self-Host installations, uptime is the User&apos;s responsibility.
            Under the Maintenance package, the Provider announces critical
            security patches within 7 days and answers email support within 48
            hours.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">7. Limitation of Liability</h2>
          <p>
            The Provider is not liable for indirect damages (loss of profit, loss
            of data, business interruption). Total liability is limited to the
            amount paid in the last 12 months. This limit does not apply in cases
            of intent or gross negligence.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">8. Third-Party APIs</h2>
          <p>
            ABS connects to the Anthropic Claude API, Groq, Cerebras, Google
            Gemini, Cloudflare Workers AI and Cohere APIs. Those providers&apos;
            own terms of use apply; keeping your API keys safe is your
            responsibility.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">9. Termination</h2>
          <p>
            The User may stop using the service at any time. In the event of a
            material breach of this agreement, the Provider reserves the right to
            terminate the license with 14 days&apos; notice.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">10. Governing Law</h2>
          <p>
            This agreement is governed by the laws of the Kingdom of Spain.
            Disputes are settled in the courts of Barcelona, without prejudice to
            mandatory consumer law.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">11. Updates</h2>
          <p>
            The Provider reserves the right to update these terms. Material
            changes are announced 30 days in advance by email to the registered
            address.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">12. Contact</h2>
          <p>
            For questions about this agreement, write to{" "}
            <a href="mailto:legal@automatiabcn.com" className="underline">
              legal@automatiabcn.com
            </a>
            .
          </p>
        </section>
      </div>
    </main>
  );
}
