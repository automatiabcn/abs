/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

// Real captures of the running panel (dark teal theme, v1.0.6), taken from a
// live install — not a mockup. The section that used to sit here was an empty
// "Demo video coming soon." box, which is a call to look that points at
// nothing. Screens rotate on their own; the tabs jump straight to one.
type Screen = {
  src: string;
  tab: string;
  crumb: string;
  caption: string;
};

const SCREENS: Screen[] = [
  {
    src: "/product/chat.jpg",
    tab: "Chat",
    crumb: "Ask anything",
    caption:
      "One chat drives the whole system — it picks the model, calls the tools, and shows you who answered and what it cost.",
  },
  {
    src: "/product/workflows.jpg",
    tab: "Workflows",
    crumb: "Automations",
    caption:
      "Schedule multi-step jobs. Every step is a tool call you can read, re-run and audit after the fact.",
  },
  {
    src: "/product/graph.jpg",
    tab: "Context graph",
    crumb: "Retrieval",
    caption:
      "A symbol-aware map of your own documents and code — not embedding-only search that guesses.",
  },
  {
    src: "/product/growth.jpg",
    tab: "Growth",
    crumb: "Dashboard",
    caption:
      "Every run, cost and provider on one screen — real numbers, read off your own server.",
  },
];

const CYCLE_MS = 4200;

export default function ProductGallery() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = useRef(false);

  useEffect(() => {
    // matchMedia is absent in jsdom and some non-browser contexts; treat its
    // absence as "no reduced-motion preference expressed" rather than crashing
    // the whole section.
    if (typeof window === "undefined" || typeof window.matchMedia !== "function")
      return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reduced.current = mq.matches;
    const onChange = () => {
      reduced.current = mq.matches;
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (paused || reduced.current) return;
    const id = window.setInterval(() => {
      setActive((i) => (i + 1) % SCREENS.length);
    }, CYCLE_MS);
    return () => window.clearInterval(id);
  }, [paused]);

  const current = SCREENS[active];

  return (
    <div
      className="mx-auto mt-12 max-w-5xl"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* Stage — a browser frame holding the crossfading desktop panel, with
          the phone screen tucked into the corner on wide viewports. */}
      <div className="relative overflow-hidden rounded-xl border border-border bg-surface-sunken shadow-[0_24px_60px_-30px_rgb(var(--abs-brand-rgb)/0.45)]">
        {/* chrome */}
        <div className="flex items-center gap-2 border-b border-border-soft bg-surface px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
          <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
          <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
          <span className="ml-3 font-mono text-xs text-subtle">
            abs.your-domain.com
            <span className="text-muted-foreground"> / panel / {current.crumb}</span>
          </span>
        </div>

        <div className="relative aspect-[16/10] w-full">
          {SCREENS.map((s, i) => (
            <Image
              key={s.src}
              src={s.src}
              alt={`ABS panel — ${s.tab}`}
              fill
              sizes="(max-width: 1024px) 100vw, 1024px"
              priority={i === 0}
              className={`object-cover object-top transition-opacity duration-700 ease-out ${
                i === active ? "opacity-100" : "opacity-0"
              }`}
            />
          ))}

          {/* phone inset — the same product on a handset. Hidden below lg so it
              never crops the desktop shot on narrow screens. */}
          <div className="pointer-events-none absolute bottom-4 right-4 hidden w-[128px] overflow-hidden rounded-[1.1rem] border border-border-strong bg-canvas shadow-2xl lg:block">
            <div className="relative aspect-[9/19.5] w-full">
              <Image
                src="/product/chat-mobile.jpg"
                alt="ABS panel on mobile"
                fill
                sizes="128px"
                className="object-cover object-top"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {SCREENS.map((s, i) => (
          <button
            key={s.src}
            type="button"
            onClick={() => setActive(i)}
            aria-pressed={i === active}
            className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
              i === active
                ? "border-primary bg-primary-soft text-primary"
                : "border-border bg-surface text-muted-foreground hover:border-border-strong hover:text-foreground"
            }`}
          >
            {s.tab}
          </button>
        ))}
      </div>

      <p className="mx-auto mt-4 max-w-xl text-center text-sm leading-relaxed text-muted-foreground">
        {current.caption}
      </p>
    </div>
  );
}
