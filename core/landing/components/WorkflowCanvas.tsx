"use client";

import { motion } from "framer-motion";
import {
  ArrowsClockwise,
  Cloud,
  Code,
  Cpu,
  Export,
  GitFork,
  Handshake,
  Robot,
} from "@phosphor-icons/react";
import type { ComponentType } from "react";

import {
  ABS_TOOL_LABELS,
  type NodeKind,
  type WorkflowDefinition,
  type WorkflowNode,
} from "@/lib/workflow";

type IconComp = ComponentType<{ className?: string; weight?: "regular" | "fill" }>;

const ICON_FOR_KIND: Record<NodeKind, IconComp> = {
  llm_call: Cpu,
  api_request: Cloud,
  conditional: GitFork,
  loop: ArrowsClockwise,
  hitl: Handshake,
  abs_tool: Robot,
  transform: Code,
  output: Export,
};

const TONE_FOR_KIND: Record<NodeKind, string> = {
  llm_call: "ring-blue-300/60 dark:ring-blue-700/60",
  api_request: "ring-emerald-300/60 dark:ring-emerald-700/60",
  conditional: "ring-zinc-300/60 dark:ring-zinc-700/60",
  loop: "ring-rose-300/60 dark:ring-rose-700/60",
  hitl: "ring-yellow-300/60 dark:ring-yellow-700/60",
  abs_tool: "ring-purple-300/60 dark:ring-purple-700/60",
  transform: "ring-sky-300/60 dark:ring-sky-700/60",
  output: "ring-teal-300/60 dark:ring-teal-700/60",
};

const KIND_LABEL: Record<NodeKind, string> = {
  llm_call: "LLM call",
  api_request: "API request",
  conditional: "Conditional",
  loop: "Loop",
  hitl: "Human approval",
  abs_tool: "ABS tool",
  transform: "Transform",
  output: "Output",
};

function triggerSummary(trigger: WorkflowDefinition["trigger"]): string {
  if (trigger.kind === "webhook") return `webhook · ${trigger.webhook_path ?? "/hook"}`;
  if (trigger.kind === "cron") return `cron · ${trigger.cron_expr ?? "* * * * *"}`;
  if (trigger.kind === "event") return `event · ${trigger.event_topic ?? "abs.event"}`;
  return "manual";
}

export default function WorkflowCanvas({
  workflow,
  selectedNodeId,
  onSelectNode,
}: {
  workflow: WorkflowDefinition;
  selectedNodeId?: string;
  onSelectNode?: (id: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 ring-1 ring-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-zinc-50/10">
      <header className="mb-6 flex flex-col gap-1">
        <h2
          data-testid="workflow-canvas-title"
          className="text-xl font-semibold text-zinc-900 dark:text-zinc-50"
        >
          {workflow.name}
        </h2>
        <span
          data-testid="workflow-canvas-trigger"
          className="inline-flex w-fit items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
        >
          {triggerSummary(workflow.trigger)}
        </span>
        {workflow.description && (
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
            {workflow.description}
          </p>
        )}
      </header>

      <div className="flex flex-col items-stretch gap-2">
        {workflow.nodes.map((node, i) => {
          const next = workflow.nodes[i + 1];
          return (
            <div key={node.id}>
              <NodeCard
                node={node}
                selected={node.id === selectedNodeId}
                onSelect={() => onSelectNode?.(node.id)}
                index={i}
              />
              {next && <EdgeArrow source={node.id} target={next.id} />}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function NodeCard({
  node,
  selected,
  onSelect,
  index,
}: {
  node: WorkflowNode;
  selected: boolean;
  onSelect: () => void;
  index: number;
}) {
  const Icon = ICON_FOR_KIND[node.kind];
  const tone = TONE_FOR_KIND[node.kind];
  const toolLabel = node.config?.tool_name ? ABS_TOOL_LABELS[node.config.tool_name] : undefined;
  return (
    <motion.button
      type="button"
      onClick={onSelect}
      data-testid={`workflow-node-${node.id}`}
      aria-pressed={selected}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.25 }}
      className={
        "flex w-full items-start gap-3 rounded-2xl bg-zinc-50 p-4 text-left transition ring-1 hover:ring-zinc-400 dark:bg-zinc-900 " +
        tone +
        (selected ? " ring-2 ring-zinc-900 dark:ring-zinc-50" : "")
      }
    >
      <span className="rounded-xl bg-white p-2 ring-1 ring-zinc-900/5 dark:bg-zinc-950 dark:ring-zinc-50/10">
        <Icon className="size-5 text-zinc-700 dark:text-zinc-200" weight="regular" />
      </span>
      <span className="flex flex-1 flex-col">
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          {node.name}
        </span>
        <span className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
          {KIND_LABEL[node.kind]}
        </span>
        {toolLabel && (
          <span className="mt-2 inline-flex w-fit items-center rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-900 dark:bg-purple-900/30 dark:text-purple-200">
            {toolLabel}
          </span>
        )}
      </span>
    </motion.button>
  );
}

function EdgeArrow({ source, target }: { source: string; target: string }) {
  return (
    <div
      data-testid={`workflow-edge-${source}-${target}`}
      className="flex flex-col items-center py-1"
    >
      <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
        success
      </span>
      {/* VQ-008 — 1px duz edge, dekoratif comet/glow yok. */}
      <svg width="16" height="20" viewBox="0 0 16 20" aria-hidden="true">
        <line
          x1="8"
          y1="2"
          x2="8"
          y2="16"
          stroke="currentColor"
          strokeWidth="1"
          className="text-zinc-400"
        />
        <polyline
          points="3,12 8,18 13,12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          className="text-zinc-400"
        />
      </svg>
    </div>
  );
}
