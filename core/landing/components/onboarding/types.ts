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
