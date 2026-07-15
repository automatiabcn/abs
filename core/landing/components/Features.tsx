/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

interface Feature {
  title: string;
  description: string;
}

const FEATURES: Feature[] = [
  {
    title: "100+ MCP tools",
    description:
      "Installed and ready, and extensible. You can add your own tools (measured: 120 tools).",
  },
  {
    title: "13 quality pipelines",
    description:
      "qual-code, qual-tr, qual-analysis, judge — production flows that chain several models together.",
  },
  {
    title: "6-provider cascade",
    description:
      "Anthropic, Groq, Cerebras, Gemini, CloudFlare, Cohere — if one goes down, the next takes over.",
  },
  {
    title: "Symbol-aware RAG",
    description:
      "A 10K+ symbol index and a callsite graph — this is where it parts ways with embedding-only search.",
  },
  {
    title: "Senior Judge",
    description:
      "Combines AST metrics with an LLM verdict on each diff to produce a quality score.",
  },
  {
    title: "Turkish quality pipeline",
    description:
      "A generate-check-polish flow built specifically for Turkish on multilingual models.",
  },
  {
    title: "16-second warm boot",
    description: "One Docker Compose command. Cold start is 16s with a cached image, and the first install takes minutes. Anyone who knows SSH can set it up.",
  },
  {
    title: "6 months of dogfooding",
    description:
      "The founder uses it every day — every feature came out of real work.",
  },
];

const Features: FC = () => (
  <section
    id="features"
    aria-labelledby="features-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="features-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        What comes in the box
      </h2>
      <p className="mt-4 text-muted-foreground">
        You do not depend on any plugin marketplace — it is all in the repo.
      </p>
    </div>

    <ul className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {FEATURES.map((f) => (
        <li
          key={f.title}
          className="rounded-lg border border-border bg-card p-6 text-left shadow-sm"
        >
          <h3 className="text-base font-semibold">{f.title}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{f.description}</p>
        </li>
      ))}
    </ul>
  </section>
);

export default Features;
