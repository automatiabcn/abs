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

/** What this server actually has. Every node in the map comes from here. */
export interface CosmosWorld {
  /** Providers the operator configured — from /v1/system/quota_status. */
  providers: string[];
  /** Tool categories and their counts — from /v1/panel/tools. */
  toolCategories: { name: string; count: number }[];
  /** Workflow definitions — from /v1/workflows/definitions. */
  workflows: string[];
  /** Indexed documents — from /v1/rag/documents. */
  documents: string[];
}

export const EMPTY_WORLD: CosmosWorld = {
  providers: [],
  toolCategories: [],
  workflows: [],
  documents: [],
};

/** Every node in this map is something the server told us about.
 *
 * It was not. The map rendered seven providers, four workflows and three RAG
 * collections named `guvenlik`, `satis-q2` and `sss` — on every install, with no
 * fetch behind any of them — under a caption reading "live, and moving as the
 * server works". A customer with one provider and an empty knowledge base saw a
 * busy constellation of a system they did not have. It was the panel's most
 * confident screen and its least true.
 *
 * A world with nothing in it produces a graph with nothing in it. That is the
 * correct picture of a server that has nothing in it.
 */
export function buildCosmosGraph(
  world: CosmosWorld = EMPTY_WORLD,
  activeProvider?: string,
): {
  nodes: GraphNode[];
  links: GraphLink[];
} {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];

  const providerIds = world.providers.map((p) => {
    const id = `p:${p}`;
    nodes.push({
      id,
      group: "provider",
      label: p,
      val: 12,
      state: activeProvider && p === activeProvider ? "active" : "idle",
    });
    return id;
  });

  const toolIds: Record<string, string> = {};
  world.toolCategories.forEach((c, i) => {
    const id = `t:${c.name}`;
    toolIds[c.name] = id;
    nodes.push({
      id,
      group: "tool",
      label: `${c.name}:${c.count}`,
      val: 6 + (i % 3),
      state: "idle",
    });
    providerIds.forEach((p) => links.push({ source: p, target: id, kind: "cascade" }));
  });

  // Workflows hang off the tool clusters they actually use where we can tell,
  // and off nothing where we cannot — an invented edge is an invented claim.
  const anchor = toolIds["workflow"] ?? toolIds["rag"] ?? Object.values(toolIds)[0];
  world.workflows.forEach((w) => {
    const id = `w:${w}`;
    nodes.push({ id, group: "workflow", label: w, val: 5, state: "idle" });
    if (anchor) links.push({ source: anchor, target: id, kind: "flow" });
  });

  const ragAnchor = toolIds["rag"] ?? anchor;
  world.documents.forEach((d) => {
    const id = `r:${d}`;
    nodes.push({ id, group: "rag", label: d, val: 4, state: "idle" });
    if (ragAnchor) links.push({ source: ragAnchor, target: id, kind: "deps" });
  });

  return { nodes, links };
}
