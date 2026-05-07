/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R04 / T-R06 — onboarding step IDs + i18n-driven copy.
// Copy lives in `locales/<lang>.json` under keys
// `onboarding.<id>.{title,body,cta}`. The `OnboardingFlow` component reads
// the active lang and rebuilds the array via `buildOnboardingSteps(lang)`.
import { t, type Lang } from "@/lib/i18n";
import type { OnboardingStep, OnboardingStepId } from "./types";

const STEP_IDS: OnboardingStepId[] = [
  "workspace",
  "project",
  "invite",
  "rag-ingest",
  "rag-query",
];

export function buildOnboardingSteps(lang: Lang): OnboardingStep[] {
  return STEP_IDS.map((id) => ({
    id,
    title: t(`onboarding.${id}.title`, lang),
    body: t(`onboarding.${id}.body`, lang),
    cta: t(`onboarding.${id}.cta`, lang),
    attachTo: `[data-onboard="${id}"]`,
  }));
}

// Default English steps for callers without a lang context (e.g. the
// `STEP_GLYPH` mapping which only needs the IDs).
export const ONBOARDING_STEPS: OnboardingStep[] = buildOnboardingSteps("en");
