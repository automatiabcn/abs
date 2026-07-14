/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Drop-off analytics. Posts events to /api/onboarding/event;
// the backend forwards to LangFuse so we can build a funnel chart.
//
// Failure mode is silent: walkthrough must keep working even if the
// analytics endpoint is unreachable.
import type { OnboardingStepId } from "./types";

export type OnboardingEventName =
  | "onboarding.start"
  | "onboarding.step.shown"
  | "onboarding.step.completed"
  | "onboarding.step.skipped"
  | "onboarding.complete"
  | "onboarding.dismissed";

export interface OnboardingEvent {
  name: OnboardingEventName;
  step?: OnboardingStepId;
  meta?: Record<string, string | number | boolean>;
}

const ENDPOINT = "/api/onboarding/event";

export async function record(event: OnboardingEvent): Promise<void> {
  try {
    await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...event,
        ts: Date.now(),
        ua: typeof navigator !== "undefined" ? navigator.userAgent : "",
      }),
      // `keepalive` lets the request survive a navigation/unmount.
      keepalive: true,
    });
  } catch (_e) {
    // Analytics outage must never block the walkthrough.
  }
}
