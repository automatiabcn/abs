/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The usage guide: what a developer actually does, in the order they do it.
//
// Every screenshot below was taken from the running editor while performing
// the step it illustrates — the searches really ran, the checks really passed,
// the answer really came back from cerebras for $0.0015. Where a panel is
// empty in the product it is empty here, and where ABS refused something the
// refusal is shown rather than cropped out. A guide that shows a state the
// software cannot reach teaches the wrong thing twice: once when it is read,
// and again when it is contradicted.
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: { absolute: "Using ABS Studio — a guide · ABS Studio" },
  description:
    "What you actually do with ABS Studio, step by step: ask about code, get a graded proposal, run your checks in a sandbox, commit with evidence, and search what the engine knows.",
};

const INK = "#0b1016";
const INK_SOFT = "#0a0f16";
const LINE = "#1b2735";
const TEXT = "#cdd8e6";
const MUTED = "#8296ad";
const TEAL = "#34d8c4";

function Shot({
  src,
  alt,
  width,
  height,
  caption,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  caption: string;
}) {
  return (
    <figure className="mt-5">
      <div
        className="overflow-hidden rounded-lg border"
        style={{ borderColor: LINE, background: INK_SOFT }}
      >
        <Image
          src={src}
          alt={alt}
          width={width}
          height={height}
          sizes="(max-width: 768px) 100vw, 620px"
          style={{ width: "100%", height: "auto" }}
        />
      </div>
      <figcaption className="mt-2 text-xs" style={{ color: MUTED }}>
        {caption}
      </figcaption>
    </figure>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-16 scroll-mt-20" id={`step-${n}`}>
      <p
        className="font-mono text-xs uppercase tracking-[0.18em]"
        style={{ color: TEAL }}
      >
        {n}
      </p>
      <h2
        className="mt-2 text-2xl font-semibold tracking-tight"
        style={{ color: "#eaf2ff" }}
      >
        {title}
      </h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed" style={{ color: MUTED }}>
        {children}
      </div>
    </section>
  );
}

export default function GuidePage() {
  return (
    <div style={{ background: INK, color: TEXT }}>
      <main className="mx-auto max-w-3xl px-5 py-20 sm:py-24">
        <p
          className="font-mono text-xs uppercase tracking-[0.2em]"
          style={{ color: TEAL }}
        >
          ABS Studio · guide
        </p>
        <h1
          className="mt-4 text-3xl font-bold leading-tight tracking-tight sm:text-4xl"
          style={{ color: "#eaf2ff" }}
        >
          Using ABS Studio
        </h1>
        <p className="mt-4 text-base leading-relaxed" style={{ color: MUTED }}>
          Everything here is a real capture of the editor doing the thing being
          described. Where the panel was empty, it is empty in the picture;
          where ABS refused to do something, the refusal is in the picture too.
          If you have not installed it yet, start with the{" "}
          <Link href="/docs/install" className="underline">
            install guide
          </Link>
          .
        </p>

        {/* --- contents ------------------------------------------------- */}
        <nav className="mt-10 rounded-lg border p-5" style={{ borderColor: LINE, background: INK_SOFT }}>
          <p className="text-xs uppercase tracking-wider" style={{ color: MUTED }}>
            In this guide
          </p>
          <ol className="mt-3 space-y-1.5 text-sm">
            {[
              ["step-01", "Give it a provider key"],
              ["step-02", "Ask about the code in front of you"],
              ["step-03", "Ask for a change, and read the grade"],
              ["step-04", "Prove it before you commit"],
              ["step-05", "Commit with evidence, push on purpose"],
              ["step-06", "Teach it your codebase"],
              ["step-07", "Watch what it costs"],
              ["step-08", "The work beside the code"],
            ].map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="underline" style={{ color: TEXT }}>
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        {/* --- 01 -------------------------------------------------------- */}
        <Step n="01" title="Give it a provider key">
          <p>
            ABS routes to free tiers first, so the cheapest way to start is a
            free-tier key from Groq, Cerebras or Gemini. Open the Command
            Palette and run <strong style={{ color: TEXT }}>ABS: Add a provider key</strong>,
            pick the provider, and paste the key.
          </p>
          <p>
            The key is checked with the provider <em>before</em> it is stored.
            If it is wrong you are told immediately rather than discovering it
            later as a failed request — and the panel will say
            <em> stored, but not verified</em> rather than green-lighting a key
            nobody has seen work.
          </p>
          <p>
            The title bar is the readout: how many providers are ready, how many
            models they expose, and what today has cost.
          </p>
          <Shot
            src="/product/detail-titlebar.webp"
            alt="The editor title bar reading admin at abs dot local, five providers ready, five models, one hundred per cent free."
            width={1044}
            height={46}
            caption="Five providers configured, five models, and nothing spent — free-tier routing is the default."
          />
        </Step>

        {/* --- 02 -------------------------------------------------------- */}
        <Step n="02" title="Ask about the code in front of you">
          <p>
            The Chat section answers questions about what you have open. Every
            answer is signed: which provider replied, how long it took, and
            what it cost.
          </p>
          <p>
            <strong style={{ color: TEXT }}>Select the code you are asking about.</strong>{" "}
            ABS never uploads a whole file quietly — you should always know what
            you just sent — so with nothing selected the model gets your question
            and a filename, and it will answer anyway. When that happens the
            answer says so, because a confident answer written without seeing
            your code is the most expensive kind of wrong.
          </p>
          <Shot
            src="/product/guide-chat.webp"
            alt="An answer in the Chat panel followed by the line: answered without seeing your code — select some and ask again · answered by cerebras · 1.1s · $0.0015."
            width={584}
            height={180}
            caption="A real answer, and a real warning: this one was asked with nothing selected, and the reply invented a function that does not exist."
          />
        </Step>

        {/* --- 03 -------------------------------------------------------- */}
        <Step n="03" title="Ask for a change, and read the grade">
          <p>
            Describe what you want in the Composer box. What comes back is not
            a diff to accept on faith: a senior judge scores it, a code graph
            works out the blast radius, and the patch engine tries it against
            the file as it is on disk.
          </p>
          <p>
            Those are independent checks and they can disagree. A proposal can
            score well and still be refused — that is the design working, not a
            fault. <strong style={{ color: TEXT }}>A good score is not permission.</strong>
          </p>
          <Shot
            src="/product/proposal-graded.webp"
            alt="A graded proposal: a green Judge 9.0 badge, a high blast-radius badge, a unified diff, the judge's note suggesting ZeroDivisionError instead of ValueError, a greyed-out Approve button beside an active Reject, and the line answered by groq free."
            width={1400}
            height={860}
            caption="Judge 9.0, a useful note — and Approve greyed out, because the model invented a line of context that is not in the file."
          />
          <p>
            Read the note before the diff. It is where the judge says what it
            would have done differently, which is usually worth more than the
            score.
          </p>
        </Step>

        {/* --- 04 -------------------------------------------------------- */}
        <Step n="04" title="Prove it before you commit">
          <p>
            <strong style={{ color: TEXT }}>Review my changes</strong> grades
            everything in your working tree — your edits as well as ABS&apos;s —
            a score per file, what each one touches, and why.
          </p>
          <p>
            <strong style={{ color: TEXT }}>Run checks</strong> finds your test
            command and runs it inside the OS&apos;s own sandbox: seatbelt on
            macOS, bubblewrap on Linux, a restricted token on Windows. If no
            sandbox is available ABS says so and does not pretend.{" "}
            <em>No checks ran</em> is never reported as <em>checks passed</em>.
          </p>
          <Shot
            src="/product/guide-checks.webp"
            alt="A check result card: the command python3 -m pytest -q with a green passed badge, and beneath it the line ran in seatbelt, network off, 767 milliseconds, exit 0."
            width={584}
            height={117}
            caption="The command it chose, the sandbox it used, whether the network was off, how long it took and the exit code. A green tick with nothing behind it is not a result."
          />
        </Step>

        {/* --- 05 -------------------------------------------------------- */}
        <Step n="05" title="Commit with evidence, push on purpose">
          <p>
            A commit contains only the files ABS wrote <em>and</em> git agrees
            have changed. It is never a blanket <code>git add -A</code> that
            sweeps up whatever else you had in progress.
          </p>
          <p>
            The message says what was graded, what ran, and what did not. If no
            checks ran it says that; if they failed and you committed anyway it
            says that too.
          </p>
          <p>
            <strong style={{ color: TEXT }}>Pushing always asks.</strong> And if
            you are standing on a shared branch — <code>main</code>,{" "}
            <code>master</code>, <code>develop</code>, <code>release</code>,{" "}
            <code>production</code>, <code>stable</code> — the change is moved
            to a branch of its own and your branch is left exactly where it was.
            Add your own protected names with the{" "}
            <code>abs.protectedBranches</code> setting; it can add to the list
            but never remove from it.
          </p>
          <p>
            ABS only moves a commit it can prove is its own. If you committed
            something yourself after it did, it refuses and tells you why rather
            than rearranging history it does not understand.
          </p>
        </Step>

        {/* --- 06 -------------------------------------------------------- */}
        <Step n="06" title="Teach it your codebase">
          <p>
            <strong style={{ color: TEXT }}>Index this workspace</strong> in the
            Context section builds a local knowledge base — embeddings stay on
            your machine, in your own vector store. Then search it, and you get
            the chunks themselves with their scores, not a summary of them.
          </p>
          <Shot
            src="/product/guide-knowledge.webp"
            alt="The Context section: a knowledge search for multiply function returning three hits with scores 1.000, 0.273 and 0.260, each showing its file and the matching line of code."
            width={584}
            height={610}
            caption="A real search. The top hit scores 1.000 and the third comes from a different file — which you can see, because the filename is what survives the truncation."
          />
          <p>
            An empty result says it is empty rather than pretending to be an
            error, and an unreachable index says <em>that</em> instead of
            quietly returning nothing.
          </p>
        </Step>

        {/* --- 07 -------------------------------------------------------- */}
        <Step n="07" title="Watch what it costs">
          <p>
            The Engine section shows today&apos;s spend and the projection for
            the month, above the routing order — which providers will be tried,
            and in which sequence. Activity shows the other half: what actually
            ran, and how the work has been scoring lately.
          </p>
          <Shot
            src="/product/detail-chain.webp"
            alt="The Activity section showing a seven-day quality reading of 5.4 average across 21 judged changes, marked stable, and noting there is no earlier window to compare against."
            width={584}
            height={262}
            caption="Twenty-one graded changes averaging 5.4 — and honest about having nothing earlier to compare against yet."
          />
          <p>
            The two are deliberately named apart: <em>routing order</em> is what
            will be tried, <em>delegation chain</em> is what actually happened.
          </p>
        </Step>

        {/* --- 08 -------------------------------------------------------- */}
        <Step n="08" title="The work beside the code">
          <p>
            Approvals waiting on you, meetings the server transcribed, tasks,
            notes and saved workflows — the things that usually live in another
            tab, kept next to the file you are editing.
          </p>
          <Shot
            src="/product/guide-meetings.webp"
            alt="The Work section on the meetings tab, showing a recording called standup.wav marked done, eleven seconds long, one speaker, not indexed, with the beginning of its transcript."
            width={584}
            height={330}
            caption="A transcribed recording with its length, speaker count and whether it made it into the knowledge base."
          />
          <p>
            Each tab tells you plainly when it has nothing:{" "}
            <em>nothing is waiting on you</em> rather than an empty box you have
            to interpret.
          </p>
        </Step>

        {/* --- close ----------------------------------------------------- */}
        <section className="mt-20 rounded-lg border p-6" style={{ borderColor: LINE, background: INK_SOFT }}>
          <h2 className="text-lg font-semibold" style={{ color: "#eaf2ff" }}>
            If something does not work
          </h2>
          <p className="mt-3 text-sm leading-relaxed" style={{ color: MUTED }}>
            The{" "}
            <Link href="/docs/install" className="underline">
              install guide
            </Link>{" "}
            has a section for it — the panel not loading, the editor not
            reaching the server, a provider that looks configured but does
            nothing, a licence key that is refused. Anything it does not cover:{" "}
            <a href="mailto:support@automatiabcn.com" className="underline">
              support@automatiabcn.com
            </a>
            .
          </p>
        </section>
      </main>
    </div>
  );
}
