/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The licence email has always ended with "detailed guide:
// abs.automatiabcn.com/docs/install" and told the buyer to run install.sh
// "from the package you downloaded". Audited 08-01: the route did not exist
// and no download had ever been offered — a paying customer received a key,
// a dead link, and instructions for a file they did not have. This page is
// the destination that sentence promised.
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: { absolute: "Install ABS Studio · ABS Studio" },
  description:
    "Download ABS Studio, install the self-hosted server, and enter your licence key. Requirements, step-by-step setup, and what to do when something does not start.",
};

// The source repository is private and stays that way, so downloads come
// from this domain rather than GitHub Releases — the same shape Cursor
// uses. /download is the one page that knows where the files are.
const DOWNLOADS = "/download";

export default function InstallPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Install ABS Studio
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Two pieces: the editor you write in, and the server that runs on your
        own machine. Both are yours — nothing you index or edit leaves it.
      </p>

      <div className="prose prose-neutral mt-8 space-y-8 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">Before you start</h2>
          <ul className="ml-5 list-disc space-y-1">
            <li>
              <strong>Docker</strong> — Desktop on macOS or Windows, Engine on
              Linux. The server runs in containers; this is the one dependency.
            </li>
            <li>
              <strong>About 6 GB of free disk</strong> for the images and the
              vector store.
            </li>
            <li>
              <strong>A provider key</strong> — Groq, Cerebras and Gemini all
              have free tiers, and ABS prefers free providers by default. You
              can add one after installing; you do not need it to start.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">1. Download</h2>
          <p>
            Builds for macOS, Linux and Windows are published on the{" "}
            <a href={DOWNLOADS} className="underline">
              download page
            </a>
            . Take the editor build for your platform and the{" "}
            <code>abs-server</code> archive from the same release — they are
            versioned together and a mismatched pair is the most common cause
            of a panel that will not connect.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">2. Start the server</h2>
          <p>
            Unpack the server archive and run the installer from inside it:
          </p>
          <pre className="overflow-x-auto rounded bg-muted p-3">
            <code>{`tar xzf abs-server-*.tar.gz\ncd abs-server\n./install.sh`}</code>
          </pre>
          <p>
            It checks Docker is running, generates the signing secret for your
            install, brings up the services, and prints the panel URL — by
            default <code>http://localhost:8000</code>. The secret it writes is
            what every licence and session on this machine is signed with, so
            keep the directory it created.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">3. Enter your licence key</h2>
          <p>
            Open the panel, and paste the key from your purchase email into the
            activation box. Every install also begins with a{" "}
            <strong>seven-day trial</strong>, so the editor works before you
            have a key at all — the key is what keeps it working afterwards.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. Open the editor</h2>
          <p>
            Install the editor build the way your platform expects (drag to
            Applications on macOS, the <code>.deb</code>/<code>.tar.gz</code> on
            Linux, the installer on Windows). On first launch it looks for the
            server on <code>localhost:8000</code>. If yours runs elsewhere, set
            the address in <em>Settings → ABS → Server URL</em>.
          </p>
          <p>
            Then add a provider key from the Command Palette:{" "}
            <strong>ABS: Add a provider key</strong>. ABS asks the provider
            whether the key authenticates before it stores it, so a key that
            was mistyped tells you immediately instead of failing later.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">When something does not start</h2>
          <ul className="ml-5 list-disc space-y-2">
            <li>
              <strong>The panel does not load.</strong> Check the containers are
              up with <code>docker compose ps</code> from the server directory.
              A container in a restart loop usually means the port is already
              taken — <code>install.sh</code> reports which one.
            </li>
            <li>
              <strong>The editor says the server is unreachable.</strong> That
              is the editor being honest rather than pretending to be offline:
              the address in Settings is not answering. Confirm the panel opens
              in a browser first.
            </li>
            <li>
              <strong>A provider shows as configured but nothing runs.</strong>{" "}
              Re-add the key. ABS validates keys on entry now, but a key stored
              before that check existed was never verified by anyone.
            </li>
            <li>
              <strong>Your licence key is refused.</strong> Keys are bound to
              the install&apos;s signing secret. If you reinstalled and did not
              keep the directory <code>install.sh</code> created, write to
              support and we will reissue.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Still stuck</h2>
          <p>
            <a href="mailto:support@automatiabcn.com" className="underline">
              support@automatiabcn.com
            </a>
            . Refunds are unconditional for 14 days — see the{" "}
            <Link href="/refund" className="underline">
              refund policy
            </Link>
            .
          </p>
        </section>
      </div>
    </main>
  );
}
