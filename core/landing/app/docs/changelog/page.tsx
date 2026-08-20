/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What changed, per version.
//
// Two links started pointing here on 2026-08-04 — the editor's releaseNotesUrl
// and the update manifest's changelog_url — and this page did not exist, so
// both 404'd from the moment they were written. My own dead links, an hour
// old, in the same shape as everything else found today.
//
// Rendered from docs/CHANGELOG.md rather than copied into JSX. A changelog
// maintained in two places is a changelog that disagrees with itself, and the
// file is the one release engineering already writes to.

import fs from "node:fs";
import path from "node:path";

import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const metadata: Metadata = {
  title: "Changelog",
  description:
    "What changed in each release of ABS Studio — the editor and the self-hosted server.",
};

function readChangelog(): string {
  // Inside this directory, put there by the prebuild step. Reading it from the
  // repo root worked locally and failed in production, because the deployment
  // uploads core/landing and nothing above it.
  const file = path.join(process.cwd(), "content", "CHANGELOG.md");
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    // Better an honest empty page than a build that fails on a missing file —
    // but say so, rather than rendering a blank that reads as "no changes".
    return "";
  }
}

export default function ChangelogPage() {
  const body = readChangelog();

  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Changelog</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        One entry per release. The version your server runs is shown in the
        panel, under Settings.
      </p>

      {body ? (
        <div className="prose prose-neutral mt-10 max-w-none text-sm dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
        </div>
      ) : (
        <p className="mt-10 rounded border border-dashed p-6 text-sm text-muted-foreground">
          The changelog could not be read for this build. That is a fault on our
          side, not a sign that nothing has changed — write to{" "}
          <a href="mailto:info@automatiabcn.com" className="underline">
            info@automatiabcn.com
          </a>{" "}
          and we will send it to you.
        </p>
      )}
    </main>
  );
}
