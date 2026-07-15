/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The "Pilot / PoC call" block that stood here offered three engagements —
// PoC, Pilot, Beta Partner — including "two weeks of custom integration ...
// with on-site support" and a limited number of beta-partner slots. This is a
// product you install yourself in fifteen minutes; the block was selling a
// consulting motion that is not what is on offer.
//
// What is left is what is true: an address, and how fast someone answers it.
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
        Questions before you install?
      </h2>
      <p className="mt-4 text-muted-foreground">
        Ask us anything about running ABS on your own infrastructure — which
        providers to start with, what it needs from a server, how the license
        works.
      </p>

      <div className="mt-10">
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
    </div>
  </section>
);

export default Contact;
