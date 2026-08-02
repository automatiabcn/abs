/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The ABS Studio product page.
//
// Two rules it is built to:
//
// 1. Every screenshot is a real capture of the running editor — window 25514
//    on 2026-08-02, cropped but never redrawn, retouched or mocked up. If a
//    panel is empty in the product it is empty here. A product page that
//    shows a state the software cannot reach is a promise the download
//    breaks.
// 2. This page is about the editor and nothing else. The wider platform is
//    not mentioned, because a buyer reading three product names on the way
//    to one purchase cannot tell what they are buying.
//
// The palette is lifted from the editor's own theme (extensions/abs-theme/
// themes/abs-dark.json) so the page and the product look like one thing:
// #0b1016 ground, #3a9dff accent, #34d8c4 second accent, #cdd8e6 text.
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  // `absolute` so the root template does not append the platform's name — on
  // this page the product is the only thing being sold.
  title: { absolute: "ABS Studio — an AI code editor that runs on your machine" },
  description:
    "An AI code editor that runs on your own machine. Every edit arrives graded, every change shows what else it touches, and checks run in a sandbox — or ABS tells you they did not.",
};

const INK = "#0b1016";
const INK_SOFT = "#0a0f16";
const LINE = "#1b2735";
const TEXT = "#cdd8e6";
const MUTED = "#8296ad";
const ACCENT = "#3a9dff";
const TEAL = "#34d8c4";

type Shot = {
  src: string;
  alt: string;
  width: number;
  height: number;
};

const FEATURES: {
  kicker: string;
  title: string;
  body: string;
  shot: Shot;
}[] = [
  {
    kicker: "Composer",
    title: "Every proposal arrives already graded",
    body:
      "Ask for a change and what comes back is not a diff to accept on faith. A senior judge scores it — part static analysis of the patch itself, part model review — and the score travels with the change, so you know how much of your attention it deserves before you spend it.",
    shot: {
      src: "/product/detail-composer.webp",
      alt: "The Composer section of the ABS panel, labelled Graded Proposal, with a task box and a Run button",
      width: 579,
      height: 256,
    },
  },
  {
    kicker: "Review",
    title: "Grade the work, then prove it",
    body:
      "Before you commit, ABS reviews everything in your working tree — yours and its own — and runs your checks in a sandbox built from the OS: seatbelt on macOS, bubblewrap on Linux, a restricted token on Windows. When no sandbox is available it says so. “No checks ran” is never reported as “checks passed.”",
    shot: {
      src: "/product/detail-review.webp",
      alt: "The Review section, headed Before you commit, with Review my changes and Run checks buttons",
      width: 579,
      height: 233,
    },
  },
  {
    kicker: "Engine",
    title: "Your keys, free providers first",
    body:
      "Bring your own keys and ABS routes to free tiers before it reaches for anything billed. The cost of today and the projection for the month sit in the panel where you can see them — not in an invoice at the end of it. Keys are checked with the provider the moment you paste one, so a mistyped key fails immediately instead of quietly later.",
    shot: {
      src: "/product/detail-engine.webp",
      alt: "The Engine section showing cascade and quota, with today and projected month both reading free",
      width: 579,
      height: 252,
    },
  },
  {
    kicker: "Activity",
    title: "A chain you can watch",
    body:
      "Multi-model pipelines run in the open: which provider answered, what was tried before it, what it cost. When a provider fails mid-question the next one picks it up, and the panel shows you that happened rather than hiding it behind a spinner.",
    shot: {
      src: "/product/detail-chain.webp",
      alt: "The Activity section showing a delegation chain with the qual_code pipeline selected and a Run chain button",
      width: 579,
      height: 234,
    },
  },
];

export default function StudioPage() {
  return (
    <div style={{ background: INK, color: TEXT }}>
      <main className="mx-auto max-w-5xl px-5 py-20 sm:py-28">
        {/* --- hero ------------------------------------------------------ */}
        <p
          className="font-mono text-xs uppercase tracking-[0.2em]"
          style={{ color: TEAL }}
        >
          ABS Studio
        </p>
        <h1
          className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl"
          style={{ color: "#eaf2ff" }}
        >
          An AI code editor that runs on your machine.
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed sm:text-lg" style={{ color: MUTED }}>
          The editor you write in and the engine behind it both run on your own
          hardware. Your code is not uploaded to be indexed, and the panel tells
          you which provider answered, what it cost, and what it did not do.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            href="/download"
            className="rounded-md px-5 py-2.5 text-sm font-semibold"
            style={{ background: ACCENT, color: "#06121f" }}
          >
            Download ABS Studio
          </Link>
          <Link
            href="/docs/install"
            className="rounded-md border px-5 py-2.5 text-sm font-medium"
            style={{ borderColor: LINE, color: TEXT }}
          >
            Install guide
          </Link>
          <span className="text-sm" style={{ color: MUTED }}>
            Seven-day trial. No key, no card.
          </span>
        </div>

        {/* --- the product, actually running ----------------------------- */}
        {/* The panel is the product, and at text-column width its labels are
            unreadable. The shot gets more room than the prose. */}
        <figure className="mt-14 lg:-mx-16 xl:-mx-28">
          <div
            className="overflow-hidden rounded-lg border"
            style={{ borderColor: LINE, background: INK_SOFT }}
          >
            <Image
              src="/product/editor-hero.webp"
              alt="ABS Studio with its own source open — the branch-protection list naming main, master, trunk, develop, release, production and stable — and the ABS panel on the right showing Chat, Composer, Review, Engine and Activity. The title bar reads five providers ready, five models, one hundred per cent free."
              width={1920}
              height={1181}
              priority
              sizes="(max-width: 1024px) 100vw, 1400px"
              style={{ width: "100%", height: "auto" }}
            />
          </div>
          <figcaption className="mt-3 text-xs" style={{ color: MUTED }}>
            A real capture of ABS Studio editing its own source, not a
            mock-up. The list on screen is the one further down this page:
            the branches ABS will not push to. Every screenshot here comes
            from the running editor.
          </figcaption>
        </figure>

        {/* --- the one-line claim the title bar already makes ------------- */}
        <section className="mt-16">
          <div
            className="overflow-hidden rounded-md border"
            style={{ borderColor: LINE }}
          >
            <Image
              src="/product/detail-titlebar.webp"
              alt="The editor title bar reading admin at abs dot local, five providers ready, five models, one hundred per cent free"
              width={1044}
              height={46}
              sizes="(max-width: 1024px) 100vw, 1024px"
              style={{ width: "100%", height: "auto" }}
            />
          </div>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed" style={{ color: MUTED }}>
            That reading is live, and it is the whole pitch in one line: the
            providers you configured, the models they expose, and what the work
            has cost so far. Free-tier routing is the default, so on most days
            that last number stays where it is.
          </p>
        </section>

        {/* --- features -------------------------------------------------- */}
        <div className="mt-20 space-y-16">
          {FEATURES.map((f) => (
            <section
              key={f.kicker}
              className="grid items-center gap-8 md:grid-cols-2"
            >
              <div>
                <p
                  className="font-mono text-xs uppercase tracking-[0.18em]"
                  style={{ color: TEAL }}
                >
                  {f.kicker}
                </p>
                <h2
                  className="mt-3 text-2xl font-semibold tracking-tight"
                  style={{ color: "#eaf2ff" }}
                >
                  {f.title}
                </h2>
                <p className="mt-3 text-sm leading-relaxed" style={{ color: MUTED }}>
                  {f.body}
                </p>
              </div>
              <div
                className="overflow-hidden rounded-lg border"
                style={{ borderColor: LINE, background: INK_SOFT }}
              >
                <Image
                  src={f.shot.src}
                  alt={f.shot.alt}
                  width={f.shot.width}
                  height={f.shot.height}
                  sizes="(max-width: 768px) 100vw, 480px"
                  style={{ width: "100%", height: "auto" }}
                />
              </div>
            </section>
          ))}
        </div>

        {/* --- the things that have no screenshot ------------------------ */}
        <section className="mt-20">
          <h2
            className="text-2xl font-semibold tracking-tight"
            style={{ color: "#eaf2ff" }}
          >
            And the parts you only notice when they save you
          </h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            {[
              [
                "Undo means before the agent",
                "Files are checkpointed before an edit lands. If you have since edited one yourself, ABS refuses the undo and tells you why rather than overwriting your work.",
              ],
              [
                "Commits carry evidence",
                "A commit holds only the files ABS wrote and git agrees have changed — never a blanket add that sweeps up yours. The message states what was graded, what ran, and what did not.",
              ],
              [
                "Pushing asks, always",
                "And a shared branch — main, master, develop, release, production, stable — sends the change to a branch of its own instead. Your branch stays where you left it.",
              ],
              [
                "Blast radius before the edit",
                "A code graph answers what refers to this, so the reach of a rename is a number you read beforehand rather than a surprise in CI.",
              ],
            ].map(([title, body]) => (
              <div
                key={title}
                className="rounded-lg border p-5"
                style={{ borderColor: LINE, background: INK_SOFT }}
              >
                <h3 className="text-sm font-semibold" style={{ color: "#eaf2ff" }}>
                  {title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed" style={{ color: MUTED }}>
                  {body}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* --- close ----------------------------------------------------- */}
        <section
          className="mt-20 rounded-lg border p-8"
          style={{ borderColor: LINE, background: INK_SOFT }}
        >
          <h2 className="text-2xl font-semibold tracking-tight" style={{ color: "#eaf2ff" }}>
            Try it for a week without giving us anything
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed" style={{ color: MUTED }}>
            Every install begins with a seven-day trial — no licence key and no
            card. Bring a free provider key and the whole editor works. Refunds
            after that are unconditional for fourteen days.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link
              href="/download"
              className="rounded-md px-5 py-2.5 text-sm font-semibold"
              style={{ background: ACCENT, color: "#06121f" }}
            >
              Download ABS Studio
            </Link>
            <Link
              href="/pricing"
              className="rounded-md border px-5 py-2.5 text-sm font-medium"
              style={{ borderColor: LINE, color: TEXT }}
            >
              Pricing
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}
