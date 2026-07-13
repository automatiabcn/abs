/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

const Contact: FC = () => (
  <section
    id="contact"
    aria-labelledby="contact-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="contact-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        Pilot / PoC call
      </h2>
      <p className="mt-4 text-muted-foreground">
        Get in touch to try the system in your own environment. We will work out
        together which option fits you best: pilot, PoC or beta partner.
      </p>
    </div>

    <div className="mx-auto mt-12 max-w-3xl grid gap-6 md:grid-cols-3">
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">PoC</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Helm chart, documentation and basic support. Install it on your own
          server, try it, then decide.
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">Pilot</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Two weeks of custom integration, connected to your own systems, with
          on-site support.
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">Beta Partner</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Full access for 30 days as a feedback partner. We take a limited number
          of partners.
        </p>
      </div>
    </div>

    <div className="mx-auto mt-12 max-w-xl text-center">
      <a
        href="mailto:support@automatiabcn.com"
        className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-semibold text-primary-foreground"
      >
        support@automatiabcn.com
      </a>
      <p className="mt-3 text-xs text-muted-foreground">
        We reply within 24 hours.
      </p>
    </div>
  </section>
);

export default Contact;
