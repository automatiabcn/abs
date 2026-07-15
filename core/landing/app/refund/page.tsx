/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Was a redirect to /#contact on a "pilot mode, no payments" premise. ABS now
// sells subscriptions and the Terms page links here for the refund details, so
// this is a real policy page — consistent with Terms §2/§4 and how /terms and
// /privacy are handled.
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Refund Policy",
  description:
    "Refund policy for the Automatia ABS self-host orchestrator: seven-day trial, 14-day money-back guarantee, and how cancellation works.",
};

export default function RefundPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Refund Policy
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Last updated: 15 July 2026.
      </p>

      <div className="prose prose-neutral mt-8 space-y-6 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">1. The trial comes first</h2>
          <p>
            Every install begins with a <strong>seven-day trial</strong> — no
            card and no license key. You only pay once you decide to subscribe,
            so there is nothing to refund while you are still trying ABS.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">
            2. 14-day money-back guarantee
          </h2>
          <p>
            You have an{" "}
            <strong>unconditional right to a refund within 14 days</strong> of
            any payment, no reason required. Email{" "}
            <a href="mailto:info@automatiabcn.com" className="underline">
              info@automatiabcn.com
            </a>{" "}
            from the address you used at checkout, with your order or invoice ID,
            and we refund the payment in full.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">
            3. What happens to your license
          </h2>
          <p>
            When a payment is refunded, the license key issued for it is marked{" "}
            <code>revoked_at</code> and deactivated: chat and the agent stop.
            Your data is untouched — documents, meetings, transcripts and
            provider keys stay on your own server, and remain readable,
            exportable and deletable.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. Cancelling a subscription</h2>
          <p>
            You can cancel any month. Cancelling stops the next renewal; the
            subscription runs to the end of the period you have already paid for
            and is not pro-rated. After it lapses, chat and the agent stop
            following a seven-day grace window — and your data stays yours to
            export or delete.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">5. Contact</h2>
          <p>
            Refund requests and billing questions:{" "}
            <a href="mailto:info@automatiabcn.com" className="underline">
              info@automatiabcn.com
            </a>
            . We reply within 24 hours.
          </p>
        </section>
      </div>
    </main>
  );
}
