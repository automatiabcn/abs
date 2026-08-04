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

import { RELEASE } from "@/lib/downloads";

export const metadata: Metadata = {
  title: "Install",
  description:
    "Download ABS Studio, install the self-hosted server, and enter your licence key. Requirements, step-by-step setup, and what to do when something does not start.",
};

// The source repository is private and stays that way, so downloads come
// from this domain rather than GitHub Releases. /download is the one page
// that knows where the files are.
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

      {/* Read from the same source the download page reads, so the two pages
          cannot contradict each other — and so this note disappears by itself
          when the first release lands, rather than being a second edit
          somebody has to remember. Caught on the live site (08-02): step 1
          said builds "are published" while /download said they were not. */}
      {RELEASE === null ? (
        <div className="mt-8 rounded border border-dashed p-4 text-sm leading-relaxed">
          <p className="font-medium">Builds are not published yet.</p>
          <p className="mt-2 text-muted-foreground">
            The steps below are the real ones and will not change — but until
            the first release is out there is nothing on the download page to
            fetch. If you are installing ABS Studio now, write to{" "}
            <a href="mailto:info@automatiabcn.com" className="underline">
              info@automatiabcn.com
            </a>{" "}
            and we will send you the build.
          </p>
        </div>
      ) : null}

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
            Builds for macOS, Linux and Windows {RELEASE === null ? "will be" : "are"}{" "}
            published on the{" "}
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
          {/*
            Kept in step with what install.sh does, because it stopped being in
            step the moment the installer changed. This said `cd abs-server`,
            and the archive extracts to a versioned directory, so the second
            line of the first instruction failed. It also called the panel
            http://localhost:8000 — that is the address the *editor* uses; the
            panel is behind Caddy on https. Two wrong facts in four lines, both
            introduced by improving the installer without rereading the page
            that describes it.
          */}
          <pre className="overflow-x-auto rounded bg-muted p-3">
            <code>{`tar xzf abs-server-*.tar.gz\ncd abs-server-*\n./install.sh`}</code>
          </pre>
          <p>
            It checks Docker, fills in the settings it can work out for itself —
            the address, a database password, the image build for your
            processor — pulls the images and starts everything. There is nothing
            to edit first.
          </p>
          <p>
            When it finishes it prints two addresses: the <strong>panel</strong>{" "}
            at <code>https://localhost</code>, and the address to give the{" "}
            <strong>editor</strong>, usually <code>http://localhost:8000</code>.
            They differ on purpose — the panel is served through a reverse proxy
            with its own certificate, which your machine has no reason to trust,
            and the editor cannot be told to ignore that. If something else on
            your machine already uses port 8000 the installer moves to the next
            free one and tells you which.
          </p>
          <p>
            Keep the directory it created. The <code>.env</code> inside it holds
            your database password and the secret every licence and session on
            this machine is signed with.
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
            Linux, the installer on Windows).
          </p>
          <p>
            The server installer already pointed the editor at itself, so there
            is usually nothing to configure. It only does that when the editor
            has no settings file yet — an existing one is yours, and it says so
            rather than rewriting it. If you need to set the address by hand it
            is <code>abs.serverUrl</code>, under{" "}
            <em>Settings → Extensions → ABS</em>, and the value is the one the
            installer printed.
          </p>
          <p>
            Then add a provider key from the Command Palette:{" "}
            <strong>ABS: Add a provider key</strong>. ABS asks the provider
            whether the key authenticates before it stores it, so a key that
            was mistyped tells you immediately instead of failing later.
          </p>
          <p>Where to get one — none of these need a card:</p>
          <ul className="ml-5 list-disc space-y-2">
            <li>
              <strong>Groq</strong> — <code>console.groq.com/keys</code>. A good
              first key: it leads the free chain by default.
            </li>
            <li>
              <strong>Cerebras</strong> — <code>cloud.cerebras.ai</code>.
            </li>
            <li>
              <strong>Gemini</strong> — <code>aistudio.google.com/apikey</code>.
            </li>
            <li>
              <strong>Ollama</strong> — <code>ollama.com</code>, if you would
              rather nothing left the machine at all. Point the server at it and
              ABS puts it ahead of anything paid.
            </li>
          </ul>
          <p>
            <strong>Already paying for ChatGPT Plus, Claude Pro or Google AI
            Pro?</strong> Those are subscriptions to the chat apps, not API
            credit, so there is no key to paste — but each vendor ships a CLI
            the subscription covers, and ABS can drive it. Install the CLI on
            the machine your server runs on, sign in once in the browser it
            opens, and ABS picks it up:
          </p>
          <ul className="ml-5 list-disc space-y-2">
            <li>
              <strong>ChatGPT Plus / Pro</strong> —{" "}
              <code>npm install -g @openai/codex</code>, then{" "}
              <code>codex login</code>.
            </li>
            <li>
              <strong>Claude Pro / Max</strong> —{" "}
              <code>npm install -g @anthropic-ai/claude-code</code>, then run{" "}
              <code>claude</code> once.
            </li>
            <li>
              <strong>Google AI Pro</strong> — the Antigravity CLI, then run{" "}
              <code>agy</code> once.
            </li>
          </ul>
          <p>
            Nothing is stored on our side and nothing is stored by ABS: the
            session belongs to your account, on your machine. These start in
            seconds rather than milliseconds, so ABS uses them for the deep
            work — proposals and reviews — and keeps the fast paths on the
            free tiers.
          </p>
          <p>
            One key is enough to start. ABS runs at whatever level the keys you
            brought allow, and the editor says which capability the next key
            would unlock — a second provider from a different vendor is what
            turns failover and the second opinion on.
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
          <h2 className="text-lg font-semibold">Next: actually using it</h2>
          <p>
            The{" "}
            <Link href="/docs/guide" className="underline">
              usage guide
            </Link>{" "}
            walks through what you do day to day — asking about code, reading a
            graded proposal, running your checks in a sandbox, committing with
            evidence — with a real screenshot at every step.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Still stuck</h2>
          <p>
            <a href="mailto:info@automatiabcn.com" className="underline">
              info@automatiabcn.com
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
