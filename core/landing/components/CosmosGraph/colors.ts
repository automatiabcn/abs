/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Brief 2 R3 — single brand palette for the Cosmos 3D system map.
// State (not identity) drives colour: every provider node shares the
// same hue family, distinguished only by luminance + saturation.
//
// Single-brand palette (mockup_2). Rainbow-per-provider is intentionally
// not used.

export const PALETTE = {
  bg: "#0a0e1a",
  primary: "#0e9a8f",
  highlight: "#4ecdc2",
  accent: "#8bede3",
  edge: "rgba(78, 205, 194, 0.28)",
  edgeActive: "rgba(139, 237, 227, 0.65)",
  textDim: "rgba(255,255,255,0.55)",
  textBright: "rgba(255,255,255,0.92)",
  errorTint: "#5a6f8d", // desaturated, NOT red — colour-blind safe
} as const;

export type NodeState = "idle" | "active" | "error";
export type NodeGroup = "provider" | "tool" | "workflow" | "rag";

export function colourFor(state: NodeState): string {
  switch (state) {
    case "active":
      return PALETTE.highlight;
    case "error":
      return PALETTE.errorTint;
    case "idle":
    default:
      return PALETTE.primary;
  }
}

// Group lightness multiplier — providers brightest, RAG dimmest. Same
// hue, different luminance → CB-safe via luminance + shape, never hue.
export function groupTone(group: NodeGroup): number {
  switch (group) {
    case "provider":
      return 1.0;
    case "tool":
      return 0.85;
    case "workflow":
      return 0.7;
    case "rag":
      return 0.55;
  }
}
