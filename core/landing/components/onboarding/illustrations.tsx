/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Empty-state SVG illustrations for each onboarding step.
// Single-color (currentColor), keep small (each <2 KB) so they ship inline.
import type { SVGProps } from "react";

export function WorkspaceGlyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="Workspace"
      {...props}
    >
      <rect x="20" y="32" width="80" height="56" rx="6" />
      <path d="M40 32V20a4 4 0 0 1 4-4h32a4 4 0 0 1 4 4v12" />
      <line x1="20" y1="56" x2="100" y2="56" />
      <circle cx="60" cy="44" r="2" fill="currentColor" />
    </svg>
  );
}

export function ProjectGlyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      role="img"
      aria-label="Project"
      {...props}
    >
      <path d="M24 40h28l8 8h36v44H24Z" />
      <line x1="36" y1="64" x2="84" y2="64" />
      <line x1="36" y1="76" x2="72" y2="76" />
    </svg>
  );
}

export function InviteGlyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      role="img"
      aria-label="Invite teammates"
      {...props}
    >
      <circle cx="46" cy="48" r="14" />
      <path d="M22 92c0-12 11-22 24-22s24 10 24 22" />
      <circle cx="86" cy="40" r="4" fill="currentColor" />
      <path d="M86 30v-6" />
      <path d="M86 56v6" />
      <path d="M76 36l-6-3" />
      <path d="M96 36l6-3" />
    </svg>
  );
}

export function RagIngestGlyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      role="img"
      aria-label="Ingest document"
      {...props}
    >
      <path d="M44 28h28l16 16v44a4 4 0 0 1-4 4H44a4 4 0 0 1-4-4V32a4 4 0 0 1 4-4Z" />
      <path d="M72 28v16h16" />
      <line x1="52" y1="58" x2="80" y2="58" />
      <line x1="52" y1="68" x2="76" y2="68" />
      <path d="M60 90v8m0 0-4-4m4 4 4-4" />
    </svg>
  );
}

export function RagQueryGlyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="Run query"
      {...props}
    >
      <circle cx="54" cy="54" r="22" />
      <line x1="70" y1="70" x2="92" y2="92" />
      <path d="M44 50c2-4 6-6 10-6" />
      <circle cx="64" cy="48" r="2" fill="currentColor" />
    </svg>
  );
}

import type { ReactElement } from "react";
import type { OnboardingStepId } from "./types";

export const STEP_GLYPH: Record<
  OnboardingStepId,
  (props: SVGProps<SVGSVGElement>) => ReactElement
> = {
  workspace: WorkspaceGlyph,
  project: ProjectGlyph,
  invite: InviteGlyph,
  "rag-ingest": RagIngestGlyph,
  "rag-query": RagQueryGlyph,
};
