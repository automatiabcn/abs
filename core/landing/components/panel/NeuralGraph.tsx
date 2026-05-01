// Q8 Phase L — react-force-graph-3d neural graph that replaces cosmos.
// Renders providers + MCP tool clusters + workflow nodes + RAG docs as a
// force-directed graph; cascade events are wired to highlight the
// matching provider node for ~1.5s.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

// react-force-graph-3d ships browser-only (Three.js renderer); skip SSR.
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), {
  ssr: false,
  loading: () => <Skeleton className="h-[420px] w-full" />,
});

interface GraphNode {
  id: string;
  group: "provider" | "tool" | "workflow" | "rag";
  label: string;
  val?: number;
  color?: string;
}

interface GraphLink {
  source: string;
  target: string;
  kind?: "cascade" | "deps" | "flow";
}

const PROVIDERS: GraphNode[] = [
  { id: "p:groq", group: "provider", label: "Groq", val: 14, color: "#6366f1" },
  { id: "p:cerebras", group: "provider", label: "Cerebras", val: 12, color: "#a855f7" },
  { id: "p:cloudflare", group: "provider", label: "Cloudflare", val: 12, color: "#f97316" },
  { id: "p:gemini", group: "provider", label: "Gemini", val: 12, color: "#3b82f6" },
  { id: "p:cohere", group: "provider", label: "Cohere", val: 10, color: "#ec4899" },
  { id: "p:anthropic-mock", group: "provider", label: "Anthropic Mock", val: 10, color: "#f59e0b" },
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

function buildGraph(): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodes: GraphNode[] = [...PROVIDERS];
  const links: GraphLink[] = [];

  // Tool category clusters — each cluster anchored to the dominant provider
  TOOL_CATEGORIES.forEach((c, i) => {
    const [name] = c.split(":");
    const id = `t:${name}`;
    nodes.push({
      id,
      group: "tool",
      label: c,
      val: 6 + (i % 3),
      color: "#10b981",
    });
    // every tool cluster touches every provider (cascade routing)
    PROVIDERS.forEach((p) => links.push({ source: p.id, target: id, kind: "cascade" }));
  });

  // 4 workflow nodes
  ["w:onboarding", "w:lead-triage", "w:incident", "w:digest"].forEach((id) => {
    nodes.push({
      id,
      group: "workflow",
      label: id.slice(2),
      val: 5,
      color: "#a855f7",
    });
    // workflows pull from tool clusters
    links.push({ source: "t:rag", target: id, kind: "flow" });
    links.push({ source: "t:quality", target: id, kind: "flow" });
  });

  // 3 RAG docs floating around the rag tool
  ["r:guvenlik", "r:satis-q2", "r:sss"].forEach((id) => {
    nodes.push({
      id,
      group: "rag",
      label: id.slice(2),
      val: 4,
      color: "#22d3ee",
    });
    links.push({ source: "t:rag", target: id, kind: "deps" });
  });

  return { nodes, links };
}

interface NeuralGraphProps {
  highlightProvider?: string;
  height?: number;
}

export function NeuralGraph({ highlightProvider, height = 420 }: NeuralGraphProps) {
  const [graph] = useState(() => buildGraph());
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const obs = new ResizeObserver(() => setWidth(el.clientWidth));
    obs.observe(el);
    setWidth(el.clientWidth);
    return () => obs.disconnect();
  }, []);

  const data = useMemo(() => graph, [graph]);

  return (
    <div
      ref={containerRef}
      data-test="neural-graph"
      className="w-full overflow-hidden rounded-xl border border-border bg-background/60"
      style={{ height }}
    >
      <ForceGraph3D
        graphData={data}
        width={width}
        height={height}
        nodeLabel={(n: object) => (n as GraphNode).label}
        nodeColor={(n: object) => {
          const node = n as GraphNode;
          if (highlightProvider && node.id === `p:${highlightProvider}`) {
            return "#fde047";
          }
          return node.color ?? "#888";
        }}
        nodeRelSize={4}
        backgroundColor="rgba(0,0,0,0)"
        linkColor={() => "rgba(99,102,241,0.25)"}
        linkOpacity={0.4}
        linkDirectionalParticles={1}
        linkDirectionalParticleSpeed={0.005}
        cooldownTicks={120}
      />
    </div>
  );
}

export default NeuralGraph;
