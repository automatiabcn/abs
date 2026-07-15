/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

import ProductGallery from "./ProductGallery";

const Demo: FC = () => {
  // When a screencast exists (NEXT_PUBLIC_DEMO_LOOM_URL), show it. Until then
  // the fallback is the real panel — captured from a live install — instead of
  // the "Demo video coming soon." box that used to stand here. A section that
  // invites you to look now has something to show.
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
          {loomUrl ? "A 3-minute tour of ABS" : "See the panel before you install"}
        </h2>
        <p className="mt-4 text-muted-foreground">
          {loomUrl
            ? "The setup wizard, an MCP tool call and the panel flow in one video."
            : "Real screens from a running install — chat, workflows, the context graph and the dashboard. Same panel on web and mobile."}
        </p>
      </div>

      {loomUrl ? (
        <div className="mx-auto mt-12 max-w-4xl overflow-hidden rounded-lg border border-border bg-card">
          <div
            className="relative aspect-video w-full bg-muted"
            data-testid="demo-iframe-wrapper"
          >
            <iframe
              title="ABS demo screencast"
              src={loomUrl}
              loading="lazy"
              allow="fullscreen"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          </div>
        </div>
      ) : (
        <ProductGallery />
      )}
    </section>
  );
};

export default Demo;
