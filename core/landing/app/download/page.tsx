/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The download surface. The source repository is private, so this page — not
// GitHub Releases — is where the licence email and the install guide send
// people. Until a release is published it says so plainly instead of showing
// buttons that 404.
import type { Metadata } from "next";
import Link from "next/link";

import { RELEASE, fileSize, platformLabel } from "@/lib/downloads";

export const metadata: Metadata = {
  title: "Download ABS Studio",
  description:
    "Download ABS Studio — the editor for macOS, Windows and Linux, and the self-hosted server archive that ships with it.",
};

export default function DownloadPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Download ABS Studio
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Two files: the editor for your platform, and the server that runs
        alongside it. Take them from the same release — a mismatched pair is
        the most common reason an install will not connect.
      </p>

      {RELEASE === null ? (
        <div className="mt-10 rounded border border-dashed p-6 text-sm leading-relaxed">
          <p className="font-medium">No build has been published yet.</p>
          <p className="mt-2 text-muted-foreground">
            ABS Studio is not downloadable from this page today. If you have
            already bought a licence, your key stays valid and nothing expires
            while you wait — write to{" "}
            <a href="mailto:support@automatiabcn.com" className="underline">
              support@automatiabcn.com
            </a>{" "}
            and we will send you the build directly.
          </p>
        </div>
      ) : (
        <div className="mt-10 space-y-8">
          <p className="text-sm text-muted-foreground">
            Version <strong>{RELEASE.version}</strong>, published{" "}
            {RELEASE.published}.
          </p>

          <section>
            <h2 className="text-lg font-semibold">Editor</h2>
            <ul className="mt-3 space-y-2">
              {RELEASE.editor.map((b) => (
                <li key={b.href} className="text-sm">
                  <a href={b.href} className="underline">
                    {b.label || platformLabel(b.platform)}
                  </a>
                  {fileSize(b.size) ? (
                    <span className="ml-2 text-muted-foreground">
                      {fileSize(b.size)}
                    </span>
                  ) : null}
                  {b.sha256 ? (
                    <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
                      sha256 {b.sha256}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold">Server</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Runs in Docker on your own machine.
            </p>
            <p className="mt-3 text-sm">
              <a href={RELEASE.server.href} className="underline">
                {RELEASE.server.label}
              </a>
              {fileSize(RELEASE.server.size) ? (
                <span className="ml-2 text-muted-foreground">
                  {fileSize(RELEASE.server.size)}
                </span>
              ) : null}
            </p>
            {RELEASE.server.sha256 ? (
              <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
                sha256 {RELEASE.server.sha256}
              </div>
            ) : null}
          </section>
        </div>
      )}

      <div className="mt-10 border-t pt-6 text-sm leading-relaxed">
        <p>
          Installing for the first time?{" "}
          <Link href="/docs/install" className="underline">
            Read the install guide
          </Link>{" "}
          — it covers requirements, the licence key, and what to do when
          something does not start.
        </p>
        <p className="mt-2 text-muted-foreground">
          Every install begins with a seven-day trial. No key, no card.
        </p>
      </div>
    </main>
  );
}
