/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

const Demo: FC = () => {
  // Only render the iframe when NEXT_PUBLIC_DEMO_LOOM_URL
  // is configured. Previously fell back to a literal "PLACEHOLDER" URL
  // that Loom rejects with X-Frame-Options:deny — Chromium dropped the
  // error silently but Firefox + WebKit logged it to the console,
  // tripping the cross-browser smoke test.
  const loomUrl = process.env.NEXT_PUBLIC_DEMO_LOOM_URL;
  return (
    <section
      id="demo"
      aria-labelledby="demo-title"
      className="container mx-auto px-4 py-20"
    >
      <div className="mx-auto max-w-2xl text-center">
        <h2
          id="demo-title"
          className="text-3xl font-bold tracking-tight sm:text-4xl"
        >
          A 3-minute tour of ABS
        </h2>
        <p className="mt-4 text-muted-foreground">
          The setup wizard, an MCP tool call and the panel flow in one video.
        </p>
      </div>

      <div className="mx-auto mt-12 max-w-4xl overflow-hidden rounded-lg border border-border bg-card">
        <div
          className="relative aspect-video w-full bg-muted"
          data-testid="demo-iframe-wrapper"
        >
          {loomUrl ? (
            <iframe
              title="ABS demo screencast"
              src={loomUrl}
              loading="lazy"
              allow="fullscreen"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          ) : (
            <div
              role="img"
              aria-label="Demo video coming soon"
              className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground"
            >
              Demo video coming soon.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default Demo;
