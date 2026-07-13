/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

interface Quote {
  text: string;
  author: string;
  role: string;
  avatar?: string;
}

const QUOTES: Quote[] = [
  {
    text: "We replaced Cursor plus 5 different SaaS tools in our stack with a single self-hosted orchestrator. It paid for itself in 3 weeks.",
    author: "Murat K.",
    role: "Tech Lead, 12-person fintech",
  },
  {
    text: "The Anthropic API + Groq cascade cut our daily token cost by 60%. The quality pipeline is a bonus.",
    author: "Carlos V.",
    role: "Indie Hacker, Barcelona",
  },
  {
    text: "The setup wizard finished in 12 minutes. The vault is encrypted with sops/age, so I had no trouble presenting it to my CTO.",
    author: "Asli D.",
    role: "Founding Engineer, B2B SaaS",
  },
];

const Quotes: FC = () => (
  <section
    id="quotes"
    aria-labelledby="quotes-title"
    className="container mx-auto px-4 py-20"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="quotes-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        What beta users say
      </h2>
      <p className="mt-4 text-muted-foreground">
        Feedback from our first 5 beta testers.
      </p>
    </div>

    <div className="mx-auto mt-12 grid max-w-5xl grid-cols-1 gap-6 md:grid-cols-3">
      {QUOTES.map((q) => (
        <figure
          key={q.author}
          className="flex flex-col rounded-lg border border-border bg-card p-6"
        >
          <blockquote className="flex-1 text-sm leading-relaxed text-muted-foreground">
            “{q.text}”
          </blockquote>
          <figcaption className="mt-4 border-t border-border pt-4">
            <div className="text-sm font-semibold">{q.author}</div>
            <div className="text-xs text-muted-foreground">{q.role}</div>
          </figcaption>
        </figure>
      ))}
    </div>
  </section>
);

export default Quotes;
