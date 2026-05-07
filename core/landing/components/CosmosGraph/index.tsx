/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Brief 2 R3..R4 — Cosmos 3D system map (force-directed graph).
//
// Approved variant: `mockup_2` (founder 2026-05-07).
//
// Tech stack:
//   * react-force-graph-3d (d3-force-3d under Three.js) for layout
//   * Three.js MeshPhysicalMaterial for glass-morphism node spheres
//   * Single brand palette — colour signals state, never identity
//   * `prefers-reduced-motion` swaps to <CosmosStaticFallback />
//   * Keyboard nav + ARIA on the wrapper
//   * No constant rotation — physics settles within ~3 s and stops
//
// Bundle target: ≤180 KB gz (force-graph-3d + three are dynamically
// imported so the first paint of /panel doesn't pay the cost).

"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { Skeleton } from "@/components/ui/skeleton";

import { buildCosmosGraph, type GraphNode } from "./buildGraph";
import { PALETTE, colourFor, groupTone } from "./colors";
import { CosmosStaticFallback } from "./StaticFallback";

const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), {
  ssr: false,
  loading: () => <Skeleton className="h-[420px] w-full" />,
});

export interface CosmosGraphProps {
  highlightProvider?: string;
  height?: number;
  /**
   * Render the static iso-grid fallback unconditionally — used by
   * Storybook / tests that cannot load WebGL. In normal app code, this
   * is `false` and the component reads `prefers-reduced-motion` instead.
   */
  forceStatic?: boolean;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mql.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function buildNodeMesh(node: GraphNode): THREE.Object3D {
  const tone = groupTone(node.group);
  const baseHex = colourFor(node.state ?? "idle");
  const base = new THREE.Color(baseHex).multiplyScalar(tone);
  const radius = (node.val ?? 6) * 0.6;

  const geometry = new THREE.SphereGeometry(radius, 24, 24);
  const material = new THREE.MeshPhysicalMaterial({
    color: base,
    transmission: 0.6,
    thickness: 0.5,
    roughness: 0.1,
    metalness: 0.3,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    transparent: true,
    opacity: 0.85,
    emissive: new THREE.Color(PALETTE.primary).multiplyScalar(0.18),
  });
  const mesh = new THREE.Mesh(geometry, material);

  if ((node.state ?? "idle") === "active") {
    const haloGeometry = new THREE.RingGeometry(radius * 1.3, radius * 1.55, 32);
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: PALETTE.accent,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
    });
    const halo = new THREE.Mesh(haloGeometry, haloMaterial);
    halo.rotation.x = Math.PI / 2;
    mesh.add(halo);
  }

  return mesh;
}

export function CosmosGraph({
  highlightProvider,
  height = 420,
  forceStatic = false,
}: CosmosGraphProps) {
  const reduced = usePrefersReducedMotion();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(800);

  const data = useMemo(
    () => buildCosmosGraph(highlightProvider),
    [highlightProvider],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const obs = new ResizeObserver(() => setWidth(el.clientWidth));
    obs.observe(el);
    setWidth(el.clientWidth);
    return () => obs.disconnect();
  }, []);

  if (forceStatic || reduced) {
    return (
      <CosmosStaticFallback
        height={height}
        highlightProvider={highlightProvider}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      data-testid="cosmos-graph"
      data-test="cosmos-graph"
      className="w-full overflow-hidden rounded-xl border border-border bg-background/60 outline-none focus-visible:ring-2 focus-visible:ring-[#78bdff]"
      style={{ height, background: PALETTE.bg }}
      role="region"
      aria-label="ABS provider cosmos — force-directed system map"
      tabIndex={0}
    >
      <ForceGraph3D
        graphData={data}
        width={width}
        height={height}
        nodeLabel={(n: object) => (n as GraphNode).label}
        nodeThreeObject={(n: object) => buildNodeMesh(n as GraphNode)}
        nodeRelSize={4}
        backgroundColor="rgba(0,0,0,0)"
        linkColor={(l: object) =>
          (l as { kind?: string }).kind === "flow"
            ? PALETTE.edgeActive
            : PALETTE.edge
        }
        linkOpacity={0.4}
        linkDirectionalParticles={1}
        linkDirectionalParticleSpeed={0.005}
        linkDirectionalParticleColor={() => PALETTE.accent}
        cooldownTicks={120}
        // No constant rotation; settle quickly and stop.
        warmupTicks={20}
      />
    </div>
  );
}

export default CosmosGraph;
