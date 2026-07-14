/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Primary onboarding component. Renders a stepper + animated card
// + View Transitions API for smooth step changes + Shepherd.js fallback for
// in-page tour overlays. Honours prefers-reduced-motion + slow connection.
"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { record } from "./analytics";
import { STEP_GLYPH } from "./illustrations";
import ProgressTracker from "./ProgressTracker";
import { buildOnboardingSteps, ONBOARDING_STEPS } from "./steps";
import type { OnboardingStepId } from "./types";
import { type Lang, t as i18nT } from "@/lib/i18n";

interface OnboardingFlowProps {
  /** Optional starting step. */
  initialStep?: OnboardingStepId;
  /** Active locale; defaults to `en`. */
  lang?: Lang;
  /** Called when the entire 5-step funnel is finished. */
  onComplete?: () => void;
}

const FIRST_STEP: OnboardingStepId = ONBOARDING_STEPS[0].id;

function withViewTransition(cb: () => void) {
  if (typeof document === "undefined") {
    cb();
    return;
  }
  const docWithVt = document as Document & {
    startViewTransition?: (fn: () => void) => void;
  };
  if (typeof docWithVt.startViewTransition === "function") {
    docWithVt.startViewTransition(cb);
  } else {
    cb();
  }
}

function isSlowConnection(): boolean {
  if (typeof navigator === "undefined") return false;
  const conn = (navigator as Navigator & {
    connection?: { effectiveType?: string; saveData?: boolean };
  }).connection;
  if (!conn) return false;
  if (conn.saveData === true) return true;
  return conn.effectiveType === "slow-2g" || conn.effectiveType === "2g";
}

export default function OnboardingFlow({
  initialStep,
  lang = "en",
  onComplete,
}: OnboardingFlowProps) {
  const [currentId, setCurrentId] = useState<OnboardingStepId>(
    initialStep ?? FIRST_STEP,
  );
  const [completed, setCompleted] = useState<OnboardingStepId[]>([]);
  const reduceMotion = useReducedMotion() ?? false;
  const slow = useMemo(isSlowConnection, []);
  // Animations off when the user opted out OR the network is constrained.
  const motionEnabled = !reduceMotion && !slow;
  const startedRef = useRef(false);

  // Locale-driven step copy.
  const steps = useMemo(() => buildOnboardingSteps(lang), [lang]);
  const tr = (key: string) => i18nT(key, lang);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void record({ name: "onboarding.start" });
    void record({ name: "onboarding.step.shown", step: FIRST_STEP });
  }, []);

  const currentIndex = steps.findIndex((s) => s.id === currentId);
  const step = steps[currentIndex];
  const Glyph = STEP_GLYPH[step.id];
  const isLast = currentIndex === steps.length - 1;

  const advance = useCallback(() => {
    void record({ name: "onboarding.step.completed", step: step.id });
    if (isLast) {
      setCompleted((prev) => [...prev, step.id]);
      void record({ name: "onboarding.complete" });
      onComplete?.();
      return;
    }
    const next = steps[currentIndex + 1];
    withViewTransition(() => {
      setCompleted((prev) => [...prev, step.id]);
      setCurrentId(next.id);
    });
    void record({ name: "onboarding.step.shown", step: next.id });
  }, [currentIndex, isLast, onComplete, step.id, steps]);

  const skip = useCallback(() => {
    void record({ name: "onboarding.step.skipped", step: step.id });
    if (isLast) {
      void record({ name: "onboarding.complete", meta: { skipped: true } });
      onComplete?.();
      return;
    }
    const next = steps[currentIndex + 1];
    withViewTransition(() => {
      setCurrentId(next.id);
    });
    void record({ name: "onboarding.step.shown", step: next.id });
  }, [currentIndex, isLast, onComplete, step.id, steps]);

  const dismissWalkthrough = useCallback(() => {
    void record({ name: "onboarding.dismissed", step: step.id });
    onComplete?.();
  }, [onComplete, step.id]);

  return (
    <section
      data-component="onboarding-flow"
      data-current-step={step.id}
      className="mx-auto flex w-full max-w-3xl flex-col items-center gap-8 px-4 py-12"
    >
      <ProgressTracker current={step.id} completed={completed} lang={lang} />

      <AnimatePresence mode="wait">
        <motion.article
          key={step.id}
          initial={motionEnabled ? { opacity: 0, y: 12 } : false}
          animate={motionEnabled ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
          exit={motionEnabled ? { opacity: 0, y: -8 } : { opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="flex w-full flex-col items-center gap-6 rounded-2xl border p-8 text-center"
          style={{
            background: "var(--abs-surface-raised)",
            borderColor: "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
            color: "var(--abs-foreground)",
            boxShadow: "var(--abs-shadow-rest)",
          }}
        >
          <span style={{ color: "var(--abs-brand-base)" }}>
            <Glyph />
          </span>

          <header>
            <h1 className="text-2xl font-semibold">{step.title}</h1>
            <p className="mt-3 text-sm opacity-75">{step.body}</p>
          </header>

          <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-center sm:gap-4">
            <button
              type="button"
              onClick={advance}
              data-action="advance"
              className="inline-flex h-10 items-center rounded-md px-6 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              style={{
                background: "var(--abs-brand-base)",
                color: "var(--abs-surface-base)",
              }}
            >
              {step.cta}
            </button>
            {!isLast ? (
              <button
                type="button"
                onClick={skip}
                data-action="skip"
                className="text-sm underline-offset-2 hover:underline"
                style={{
                  color:
                    "color-mix(in oklch, var(--abs-foreground) 70%, transparent)",
                }}
              >
                {tr("onboarding.skip")}
              </button>
            ) : null}
          </div>

          <button
            type="button"
            onClick={dismissWalkthrough}
            data-action="dismiss"
            className="-mt-2 text-xs underline-offset-2 hover:underline"
            style={{
              color: "color-mix(in oklch, var(--abs-foreground) 45%, transparent)",
            }}
          >
            {tr("onboarding.exit")}
          </button>
        </motion.article>
      </AnimatePresence>

      <DebugCaption reduceMotion={reduceMotion} slow={slow} tr={tr} />
    </section>
  );
}

// The footer caption is dev-only. In production we
// expose the same diagnostics via an icon-only `<details>` so a11y testers
// can verify reduced-motion + connection state without the duplicate step
// indicator competing with the progress tracker.
function DebugCaption({
  reduceMotion,
  slow,
  tr,
}: {
  reduceMotion: boolean;
  slow: boolean;
  tr: (key: string) => string;
}) {
  const motionLine = reduceMotion
    ? tr("onboarding.a11y.reduced_motion_on")
    : tr("onboarding.a11y.reduced_motion_off");
  const netLine = slow
    ? tr("onboarding.a11y.network_slow")
    : tr("onboarding.a11y.network_fast");
  const isDev = process.env.NODE_ENV === "development";
  if (isDev) {
    return (
      <p
        className="text-xs opacity-60"
        style={{ color: "var(--abs-foreground)" }}
      >
        {motionLine} · {netLine} · dev build
      </p>
    );
  }
  return (
    <details
      className="text-[11px]"
      style={{
        color: "color-mix(in oklch, var(--abs-foreground) 50%, transparent)",
      }}
    >
      <summary
        className="cursor-pointer select-none list-none"
        aria-label="Accessibility diagnostics"
      >
        {tr("onboarding.a11y.summary")}
      </summary>
      <p className="mt-1">
        {motionLine} · {netLine}
      </p>
    </details>
  );
}
