/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Brief 2 R3 — `NeuralGraph` is now a thin alias for `CosmosGraph`.
//
// The previous implementation (rainbow-per-provider react-force-graph-3d
// scene) was retired in favour of the founder-approved `mockup_2` design:
// single brand palette, glass-morphism nodes, prefers-reduced-motion
// fallback, ARIA-labelled wrapper. See
// `components/CosmosGraph/index.tsx` for the live implementation and
// `artifacts/cosmos_redesign/approval.md` for the founder approval.

"use client";

import {
  CosmosGraph,
  type CosmosGraphProps,
} from "@/components/CosmosGraph";

export type NeuralGraphProps = CosmosGraphProps;

export function NeuralGraph(props: NeuralGraphProps) {
  return <CosmosGraph {...props} />;
}

export default NeuralGraph;
