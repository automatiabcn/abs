/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Brief 2 R3 — extracted graph builder for the Cosmos 3D system map.
//
// Same data the legacy NeuralGraph used (providers + tool clusters +
// workflows + RAG docs), but with `state` semantics replacing the old
// per-node `color` field. The CosmosGraph component derives every
// rendered colour from `state` + `group`, never from raw provider id.

import type { NodeGroup, NodeState } from "./colors";

export interface GraphNode {
  id: string;
  group: NodeGroup;
  label: string;
  val?: number;
  state?: NodeState;
}

export interface GraphLink {
  source: string;
  target: string;
  kind?: "cascade" | "deps" | "flow";
}

export const PROVIDER_NODES: GraphNode[] = [
  { id: "p:groq", group: "provider", label: "Groq", val: 14, state: "idle" },
  { id: "p:cerebras", group: "provider", label: "Cerebras", val: 12, state: "idle" },
  { id: "p:cloudflare", group: "provider", label: "Cloudflare", val: 12, state: "idle" },
  { id: "p:gemini", group: "provider", label: "Gemini", val: 12, state: "idle" },
  { id: "p:cohere", group: "provider", label: "Cohere", val: 10, state: "idle" },
  { id: "p:anthropic", group: "provider", label: "Anthropic", val: 10, state: "idle" },
  { id: "p:ollama", group: "provider", label: "Ollama", val: 9, state: "idle" },
];

const TOOL_CATEGORIES = [
  "provider:44",
  "quality:16",
  "judge:8",
  "rag:5",
  "workflow:6",
  "system:8",
  "fullstack:4",
  "research:3",
];

export function buildCosmosGraph(activeProvider?: string): {
  nodes: GraphNode[];
  links: GraphLink[];
} {
  const nodes: GraphNode[] = PROVIDER_NODES.map((n) => ({
    ...n,
    state:
      activeProvider && n.id === `p:${activeProvider}` ? "active" : "idle",
  }));
  const links: GraphLink[] = [];

  TOOL_CATEGORIES.forEach((c, i) => {
    const [name] = c.split(":");
    const id = `t:${name}`;
    nodes.push({
      id,
      group: "tool",
      label: c,
      val: 6 + (i % 3),
      state: "idle",
    });
    PROVIDER_NODES.forEach((p) =>
      links.push({ source: p.id, target: id, kind: "cascade" }),
    );
  });

  ["w:onboarding", "w:lead-triage", "w:incident", "w:digest"].forEach(
    (id) => {
      nodes.push({
        id,
        group: "workflow",
        label: id.slice(2),
        val: 5,
        state: "idle",
      });
      links.push({ source: "t:rag", target: id, kind: "flow" });
      links.push({ source: "t:quality", target: id, kind: "flow" });
    },
  );

  ["r:guvenlik", "r:satis-q2", "r:sss"].forEach((id) => {
    nodes.push({
      id,
      group: "rag",
      label: id.slice(2),
      val: 4,
      state: "idle",
    });
    links.push({ source: "t:rag", target: id, kind: "deps" });
  });

  return { nodes, links };
}
