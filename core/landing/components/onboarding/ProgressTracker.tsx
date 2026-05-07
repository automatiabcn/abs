/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R04 — animated progress tracker. 5 dots + connector lines. T-R06 — i18n.
"use client";

import { motion } from "framer-motion";

import { buildOnboardingSteps } from "./steps";
import type { OnboardingStepId } from "./types";
import type { Lang } from "@/lib/i18n";

interface ProgressTrackerProps {
  current: OnboardingStepId;
  completed: OnboardingStepId[];
  lang?: Lang;
}

export default function ProgressTracker({
  current,
  completed,
  lang = "en",
}: ProgressTrackerProps) {
  const steps = buildOnboardingSteps(lang);
  return (
    <ol
      className="flex w-full max-w-2xl items-center justify-between"
      aria-label="Onboarding progress"
      data-component="onboarding-progress"
    >
      {steps.map((step, idx) => {
        const isDone = completed.includes(step.id);
        const isCurrent = step.id === current;
        const stateLabel = isDone ? "done" : isCurrent ? "current" : "pending";
        return (
          <li
            key={step.id}
            data-component="step-indicator"
            data-state={stateLabel}
            data-step={idx + 1}
            data-step-id={step.id}
            aria-current={isCurrent ? "step" : undefined}
            className="relative flex flex-1 flex-col items-center"
          >
            <motion.span
              layout
              className="grid h-8 w-8 place-items-center rounded-full text-xs font-semibold"
              style={{
                background: isDone
                  ? "var(--abs-success)"
                  : isCurrent
                    ? "var(--abs-brand-base)"
                    : "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
                color: isDone || isCurrent ? "var(--abs-surface-base)" : "var(--abs-foreground)",
                boxShadow: isCurrent
                  ? "0 0 0 4px color-mix(in oklch, var(--abs-brand-base) 25%, transparent)"
                  : "none",
              }}
            >
              {isDone ? "✓" : idx + 1}
            </motion.span>
            <span
              className="mt-2 hidden text-center text-xs sm:inline-block"
              style={{
                color: isCurrent ? "var(--abs-foreground)" : "color-mix(in oklch, var(--abs-foreground) 60%, transparent)",
              }}
            >
              {step.title}
            </span>
            {idx < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className="absolute left-1/2 top-4 h-0.5 w-full -translate-y-1/2"
                style={{
                  background: completed.length > idx
                    ? "var(--abs-success)"
                    : "color-mix(in oklch, var(--abs-foreground) 12%, transparent)",
                }}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
