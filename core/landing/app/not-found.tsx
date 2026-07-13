/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Polish round R10 — global 404. The default Next.js 404 looks nothing
// like the rest of the admin shell, which is jarring after a sidebar
// mistypo. Brand-neutral copy + return CTAs to both the public landing
// and the admin console.
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "404 — Page not found · Automatia ABS",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main
      data-test="not-found-page"
      lang="en"
      className="mx-auto flex min-h-[60vh] w-full max-w-xl flex-col items-center justify-center gap-6 px-6 py-16 text-center"
    >
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted-foreground">
        404
      </p>
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">
        Page not found
      </h1>
      <p className="text-sm text-muted-foreground">
        The page you are looking for does not exist, or it may have moved.
        Use one of the links below to get back.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          data-test="not-found-home-link"
          className="inline-flex items-center justify-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          Back to home
        </Link>
        <Link
          href="/admin/usage"
          data-test="not-found-admin-link"
          className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Go to the admin panel
        </Link>
      </div>
    </main>
  );
}
