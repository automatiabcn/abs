/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Where "Start free" lands.
//
// The hero's primary button used to say "Watch the demo" and scroll to a box
// that reads "Demo video coming soon." — the main call to action on the site,
// pointing at nothing. The product's actual front door is a one-line install
// followed by the setup wizard, so that is what the button offers now.
//
// The command is the one in the repository README, verbatim. Nothing here is a
// claim the product cannot keep: no key is required to run it, and the wizard
// says the same thing on step 2.
import type { FC } from "react";

const COMMAND = `curl -fsSL https://raw.githubusercontent.com/automatiabcn/abs/main/infra/scripts/deploy_hetzner.sh | \\
    bash -s -- --domain abs.your-domain.com --email you@your-domain.com`;

const STEPS = [
  {
    title: "Bring a Linux server",
    body: "Any VPS with Docker will do. A €5/month box is enough to start.",
  },
  {
    title: "Run one command",
    body: "It installs Docker, brings up the stack and fronts it with Caddy, which fetches a certificate for your domain.",
  },
  {
    title: "Open /setup",
    body: "Six steps: an admin account, a provider key, and a test that proves it can answer before you leave the wizard.",
  },
];

const Install: FC = () => (
  <section
    id="install"
    aria-labelledby="install-title"
    className="container mx-auto scroll-mt-20 px-4 py-20"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="install-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        Install it in about fifteen minutes
      </h2>
      <p className="mt-4 text-muted-foreground">
        On your own server, with no license key. A licence covers commercial use
        and support — it is not what makes the software run.
      </p>
    </div>

    <div className="mx-auto mt-10 max-w-3xl">
      <pre className="overflow-x-auto rounded-lg border border-border bg-card p-4 text-left text-xs leading-relaxed text-muted-foreground sm:text-sm">
        <code>{COMMAND}</code>
      </pre>

      <ol className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex flex-col gap-1">
            <span className="font-mono text-xs tabular-nums text-primary">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="text-sm font-semibold">{step.title}</span>
            <span className="text-sm text-muted-foreground">{step.body}</span>
          </li>
        ))}
      </ol>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        The full guide, and the compose file it uses, are in the{" "}
        <a
          className="underline hover:text-foreground"
          href="https://github.com/automatiabcn/abs#quick-install-15-minutes"
          rel="noreferrer"
          target="_blank"
        >
          repository
        </a>
        .
      </p>
    </div>
  </section>
);

export default Install;
