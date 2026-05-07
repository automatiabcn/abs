/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R04 — onboarding shared types.
export type OnboardingStepId =
  | "workspace"
  | "project"
  | "invite"
  | "rag-ingest"
  | "rag-query";

export interface OnboardingStep {
  id: OnboardingStepId;
  title: string;
  body: string;
  cta: string;
  /** CSS selector to attach a Shepherd tour step to (optional). */
  attachTo?: string;
}

export interface OnboardingProgress {
  completedSteps: OnboardingStepId[];
  currentStep: OnboardingStepId;
}
