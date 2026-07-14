/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

export type TriggerKind = "webhook" | "cron" | "event" | "manual";

export type NodeKind =
  | "llm_call"
  | "api_request"
  | "conditional"
  | "loop"
  | "hitl"
  | "abs_tool"
  | "transform"
  | "output";

export type EdgeKind = "success" | "error" | "conditional";

export interface WorkflowNode {
  id: string;
  kind: NodeKind;
  name: string;
  config?: {
    model?: string;
    prompt?: string;
    method?: string;
    url?: string;
    tool_name?: string;
    approval_role?: string;
    output_template?: string;
  };
}

export interface WorkflowEdge {
  source: string;
  target: string;
  kind?: EdgeKind;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string;
  trigger: {
    kind: TriggerKind;
    id: string;
    cron_expr?: string;
    webhook_path?: string;
    event_topic?: string;
  };
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  tags?: string[];
}

export const ABS_TOOL_LABELS: Record<string, string> = {
  "abs.qual_code": "Qual Code",
  "abs.qual_tr": "Qual TR",
  "abs.qual_translate": "Qual Translate",
  "abs.qual_analysis": "Qual Analysis",
  "abs.rag_query": "RAG Query",
  "abs.rag_ingest": "RAG Ingest",
  "abs.meeting_transcribe": "Meeting Transcribe",
  "abs.action_extract": "Action Extract",
  "abs.gmail_classify": "Gmail Classify",
  "abs.gmail_draft": "Gmail Draft",
  "abs.gmail_send": "Gmail Send",
  "abs.linear_create_ticket": "Linear Ticket",
  "abs.notion_log": "Notion Log",
  "abs.cerbos_check": "Cerbos Check",
  "abs.langfuse_trace": "Langfuse Trace",
};

export const NODE_COST_CENTS: Partial<Record<NodeKind, number>> = {
  llm_call: 2,
  abs_tool: 1,
  api_request: 0,
  conditional: 0,
  loop: 0,
  hitl: 0,
  transform: 0,
  output: 0,
};

export function estimateCostCents(wf: WorkflowDefinition | null | undefined): number {
  // synthesize cascade can return empty/partial bodies;
  // estimateCostCents must never crash the workflow-builder page on
  // missing `wf.nodes`. Returns 0 when the workflow shape is invalid.
  if (!wf || !Array.isArray(wf.nodes)) return 0;
  return wf.nodes.reduce(
    (sum, n) => sum + (NODE_COST_CENTS[n?.kind as NodeKind] ?? 0),
    0,
  );
}

export function isValidWorkflow(wf: unknown): wf is WorkflowDefinition {
  // canonical schema check used after `/v1/workflows/synthesize`
  // returns. Cascade providers occasionally drop required fields; treat any
  // missing piece as a synthesize failure so the UI can fall back to the
  // sample workflow + show the operator a retry CTA.
  if (!wf || typeof wf !== "object") return false;
  const w = wf as Partial<WorkflowDefinition>;
  return (
    typeof w.id === "string" &&
    typeof w.name === "string" &&
    !!w.trigger &&
    typeof w.trigger.kind === "string" &&
    Array.isArray(w.nodes) &&
    Array.isArray(w.edges)
  );
}

export const SAMPLE_WORKFLOW: WorkflowDefinition = {
  id: "rag-query-chat",
  name: "RAG-grounded customer chat",
  description: "Tenant policy check → RAG query → Compose answer",
  trigger: {
    kind: "webhook",
    id: "trg-rag-query-chat",
    webhook_path: "/hook/chat",
  },
  nodes: [
    {
      id: "node-1",
      kind: "abs_tool",
      name: "Tenant policy check",
      config: { tool_name: "abs.cerbos_check" },
    },
    {
      id: "node-2",
      kind: "abs_tool",
      name: "RAG query",
      config: { tool_name: "abs.rag_query" },
    },
    {
      id: "node-3",
      kind: "abs_tool",
      name: "Compose answer",
      config: { tool_name: "abs.qual_code", prompt: "Answer with citations." },
    },
    {
      id: "node-4",
      kind: "output",
      name: "Return JSON",
      config: { output_template: "{{result}}" },
    },
  ],
  edges: [
    { source: "node-1", target: "node-2", kind: "success" },
    { source: "node-2", target: "node-3", kind: "success" },
    { source: "node-3", target: "node-4", kind: "success" },
  ],
  tags: ["rag", "chat"],
};
