/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Purchase complete",
  robots: { index: false, follow: false },
};

interface SuccessPageProps {
  searchParams: Promise<{ session_id?: string }>;
}

export default async function SuccessPage({ searchParams }: SuccessPageProps) {
  const params = await searchParams;
  const sessionId = params.session_id ?? null;

  return (
    <main className="container mx-auto px-4 py-24">
      <div className="mx-auto max-w-2xl text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-8 w-8 text-primary"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 13l4 4L19 7"
            />
          </svg>
        </div>
        <h1 className="mt-8 text-3xl font-bold tracking-tight sm:text-4xl">
          Your purchase is complete
        </h1>
        <p className="mt-4 text-muted-foreground">
          We will email your license key within a few minutes. Your Stripe
          receipt arrives separately.
        </p>
        {sessionId && (
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Stripe session: {sessionId}
          </p>
        )}
        <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
          <Link
            href="https://abs.automatiabcn.com/docs/install"
            className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Go to the installation guide
          </Link>
          <Link
            href="/"
            className="inline-flex h-11 items-center justify-center rounded-md border border-input px-8 text-sm font-medium hover:bg-muted"
          >
            Back to home
          </Link>
        </div>
        <p className="mt-8 text-sm text-muted-foreground">
          Running into trouble?{" "}
          <a
            href="mailto:support@automatiabcn.com"
            className="underline"
          >
            support@automatiabcn.com
          </a>
        </p>
      </div>
    </main>
  );
}
