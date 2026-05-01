// Q8 Phase B / W3 — react-flow (xyflow) DAG canvas for the workflow
// builder. Replaces the vertical list canvas with a real node graph
// (zoom, pan, mini-map, controls) and a custom node renderer that mirrors
// the existing tone palette so the rest of the page stays familiar.
"use client";

import { useCallback, useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

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

import {
  ABS_TOOL_LABELS,
  type NodeKind,
  type WorkflowDefinition,
  type WorkflowNode,
} from "@/lib/workflow";
import { cn } from "@/lib/utils";

const NODE_ICON: Record<NodeKind, typeof Cpu> = {
  llm_call: Cpu,
  api_request: Cloud,
  conditional: GitFork,
  loop: ArrowsClockwise,
  hitl: Handshake,
  abs_tool: Robot,
  transform: Code,
  output: Export,
};

const NODE_TONE: Record<NodeKind, { ring: string; chip: string; label: string }> = {
  llm_call:    { ring: "ring-blue-400/60",    chip: "bg-blue-500/15 text-blue-300",       label: "LLM" },
  api_request: { ring: "ring-emerald-400/60", chip: "bg-emerald-500/15 text-emerald-300", label: "API" },
  conditional: { ring: "ring-zinc-400/60",    chip: "bg-zinc-500/15 text-zinc-300",       label: "If" },
  loop:        { ring: "ring-rose-400/60",    chip: "bg-rose-500/15 text-rose-300",       label: "Loop" },
  hitl:        { ring: "ring-amber-400/60",   chip: "bg-amber-500/15 text-amber-300",     label: "HITL" },
  abs_tool:    { ring: "ring-violet-400/60",  chip: "bg-violet-500/15 text-violet-300",   label: "Tool" },
  transform:   { ring: "ring-sky-400/60",     chip: "bg-sky-500/15 text-sky-300",         label: "Xform" },
  output:      { ring: "ring-teal-400/60",    chip: "bg-teal-500/15 text-teal-300",       label: "Out" },
};

interface WorkflowNodeData extends Record<string, unknown> {
  node: WorkflowNode;
  selected?: boolean;
}

function WorkflowNodeView({ data }: NodeProps<Node<WorkflowNodeData>>) {
  const node = data.node;
  const tone = NODE_TONE[node.kind] ?? NODE_TONE.llm_call;
  const Icon = NODE_ICON[node.kind] ?? Cpu;
  const subtitle =
    node.kind === "abs_tool" && node.config?.tool_name
      ? ABS_TOOL_LABELS[node.config.tool_name] ?? node.config.tool_name
      : node.kind === "api_request"
        ? `${node.config?.method ?? "GET"} ${node.config?.url ?? ""}`
        : node.kind === "llm_call"
          ? node.config?.model ?? "model"
          : node.kind;
  return (
    <div
      className={cn(
        "min-w-[220px] rounded-xl border border-border bg-card/95 p-3 shadow-md ring-2 backdrop-blur transition-all",
        tone.ring,
        data.selected && "scale-[1.02] ring-4",
      )}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider", tone.chip)}>
          <Icon className="size-3" />
          {tone.label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {node.id}
        </span>
      </div>
      <div className="text-sm font-semibold text-foreground">
        {node.name}
      </div>
      <div className="mt-1 truncate text-xs text-muted-foreground">
        {subtitle}
      </div>
    </div>
  );
}

const NODE_TYPES = { workflow: WorkflowNodeView };

function autoLayout(nodes: WorkflowNode[]): Record<string, { x: number; y: number }> {
  // Simple vertical spine layout — every node 160px below the previous one.
  // For a richer DAG layout (dagre/elkjs) Phase B v2 can swap this out.
  const positions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n, i) => {
    positions[n.id] = { x: 60 + (i % 2) * 40, y: 60 + i * 160 };
  });
  return positions;
}

interface WorkflowCanvasFlowProps {
  workflow: WorkflowDefinition;
  selectedNodeId?: string;
  onSelectNode?: (id: string | undefined) => void;
  onWorkflowChange?: (next: WorkflowDefinition) => void;
  readOnly?: boolean;
}

function CanvasInner({
  workflow,
  selectedNodeId,
  onSelectNode,
  onWorkflowChange,
  readOnly,
}: WorkflowCanvasFlowProps) {
  const positions = useMemo(() => autoLayout(workflow.nodes), [workflow.nodes]);

  const initialNodes = useMemo<Node<WorkflowNodeData>[]>(
    () =>
      workflow.nodes.map((n) => ({
        id: n.id,
        type: "workflow",
        position: positions[n.id] ?? { x: 0, y: 0 },
        data: { node: n, selected: n.id === selectedNodeId },
      })),
    [workflow.nodes, positions, selectedNodeId],
  );

  const initialEdges = useMemo<Edge[]>(
    () =>
      workflow.edges.map((e, i) => ({
        id: `e-${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: e.kind === "success" || e.kind == null,
        style: { stroke: e.kind === "error" ? "#f43f5e" : e.kind === "conditional" ? "#fbbf24" : "#6366f1", strokeWidth: 1.5 },
      })),
    [workflow.edges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Re-seed when the upstream workflow swaps wholesale (e.g. synthesize result)
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleConnect = useCallback(
    (conn: Connection) => {
      if (readOnly) return;
      setEdges((eds: Edge[]) => addEdge({ ...conn, animated: true }, eds));
      onWorkflowChange?.({
        ...workflow,
        edges: [
          ...workflow.edges,
          { source: conn.source ?? "", target: conn.target ?? "", kind: "success" },
        ],
      });
    },
    [readOnly, setEdges, workflow, onWorkflowChange],
  );

  const handleNodeClick = useCallback(
    (_evt: unknown, node: Node) => {
      onSelectNode?.(node.id);
    },
    [onSelectNode],
  );

  return (
    <div
      data-test="workflow-canvas-flow"
      className="h-[600px] w-full overflow-hidden rounded-2xl border border-border bg-card/40 shadow-sm"
    >
      {/* Q8 Phase B / W3 — title kept under a stable data-testid so the
          legacy WorkflowChatPanel tests (workflow-canvas-title) still pass. */}
      <div
        data-testid="workflow-canvas-title"
        className="border-b border-border bg-card/60 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
      >
        {workflow.name}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodeClick={handleNodeClick}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={1.8}
      >
        <Background gap={16} size={1} className="opacity-40" />
        <Controls className="!bg-card/80 !border-border" />
        <MiniMap
          nodeColor={(n) => {
            const tone = NODE_TONE[(n.data as WorkflowNodeData)?.node?.kind] ?? NODE_TONE.llm_call;
            return tone.ring.replace("ring-", "").includes("blue") ? "#3b82f6" : "#a855f7";
          }}
          className="!bg-background/80"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}

export default function WorkflowCanvasFlow(props: WorkflowCanvasFlowProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
