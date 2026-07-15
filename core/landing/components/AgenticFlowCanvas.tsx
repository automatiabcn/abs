/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Stage D — interactive Workflow Designer canvas (xyflow). Real editor: drag to
// reposition, drag handle-to-handle to wire/rewire, Delete to remove, click an
// agent node to inspect. Custom node renderer mirrors the mockup-03 dark tone
// (kind-coloured). The page owns nodes/edges state; this is the surface.
"use client";

import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export type FlowNodeData = {
  kind: string;
  name: string;
  desc: string;
  agent_id: string | null;
  config?: Record<string, string | number | boolean>;
  active?: boolean;
};

// kind → { box accent border, kind-label colour } — matches the agentic palette.
const TONE: Record<string, { border: string; label: string }> = {
  trigger: { border: "#38bdf8", label: "text-sky-700 dark:text-sky-300" },
  agent: { border: "#4ecdc2", label: "text-primary" },
  custom_ai: { border: "#4ecdc2", label: "text-primary" },
  consent: { border: "#d29922", label: "text-amber-700 dark:text-amber-300" },
  retrieval: { border: "#a78bfa", label: "text-violet-700 dark:text-violet-300" },
  connector: { border: "#3a4452", label: "text-muted-foreground" },
  policy: { border: "#d29922", label: "text-amber-700 dark:text-amber-300" },
  approval: { border: "#fb7185", label: "text-rose-700 dark:text-rose-300" },
  action: { border: "#3fb950", label: "text-emerald-700 dark:text-emerald-300" },
  branch: { border: "#3a4452", label: "text-muted-foreground" },
  sub_workflow: { border: "#f472b6", label: "text-pink-700 dark:text-pink-300" },
};

function AgenticNode({ data, selected }: NodeProps<Node<FlowNodeData>>) {
  const tone = TONE[data.kind] ?? TONE.connector;
  const isAgent = data.kind === "agent";
  return (
    <div
      className={`w-[150px] rounded-[10px] border bg-[#131920] px-3 py-2.5 ${selected ? "ring-2 ring-primary/70" : ""}`}
      style={{ borderColor: tone.border, boxShadow: selected ? `0 0 16px ${tone.border}40` : undefined }}
    >
      <Handle type="target" position={Position.Left} style={{ background: tone.border, width: 8, height: 8 }} />
      <div className={`font-mono text-[9px] uppercase tracking-wider ${tone.label}`}>
        {isAgent ? "⚡ " : ""}{data.kind.replace("_", "-")}
      </div>
      <div className="mt-0.5 text-[12px] font-semibold leading-tight">{data.name}</div>
      <div className="text-[10px] text-muted-foreground leading-tight">{data.desc}</div>
      <Handle type="source" position={Position.Right} style={{ background: tone.border, width: 8, height: 8 }} />
    </div>
  );
}

const NODE_TYPES = { agentic: AgenticNode };

interface Props {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  onNodesChange: OnNodesChange<Node<FlowNodeData>>;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
  onNodeClick: (id: string) => void;
}

function Inner({ nodes, edges, onNodesChange, onEdgesChange, onConnect, onNodeClick }: Props) {
  return (
    <div className="h-[440px] w-full overflow-hidden rounded-xl border" data-test="agentic-flow-canvas"
      style={{ background: "radial-gradient(circle at 30% 20%, rgba(58,157,255,.06), transparent 60%)" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_e, n) => onNodeClick(n.id)}
        nodeTypes={NODE_TYPES}
        fitView
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
        minZoom={0.4}
        maxZoom={1.8}
        defaultEdgeOptions={{ animated: true, style: { stroke: "#4ecdc2", strokeWidth: 2 } }}
      >
        <Background gap={16} size={1} className="opacity-30" />
        <Controls className="!bg-card/80 !border-border" showInteractive={false} />
        <MiniMap className="!bg-background/70" nodeColor={(n) => TONE[(n.data as FlowNodeData)?.kind]?.border ?? "#3a4452"} pannable />
      </ReactFlow>
    </div>
  );
}

export default function AgenticFlowCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
