/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What a phone, a reduced-motion setting or a slow connection gets instead of
// the WebGL scene: the same subject, standing still. Six providers on a ring,
// the vault in the middle, the spokes they answer along.
//
// The illustration it replaces was an isometric cube stack in #1e57ac/#3b82f6 —
// the retired Automatia blue — and it was `absolute inset-0`, so on the very
// devices it exists to serve it rendered *behind the headline*. It now sits in
// the hero's second column like the 3D scene it stands in for, and takes its
// colour from the brand token instead of hardcoding a palette we no longer ship.
import type { FC } from "react";

const PROVIDERS = 6;
const RADIUS = 128;
const CENTER = 160;

const nodes = Array.from({ length: PROVIDERS }, (_, i) => {
  const angle = (i / PROVIDERS) * Math.PI * 2 - Math.PI / 2;
  return {
    x: CENTER + Math.cos(angle) * RADIUS,
    y: CENTER + Math.sin(angle) * RADIUS * 0.9,
  };
});

// The mark's hexagon, drawn at two scales — the shell and the core it holds.
function hexPoints(r: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const a = (i / 6) * Math.PI * 2 - Math.PI / 2;
    return `${CENTER + Math.cos(a) * r},${CENTER + Math.sin(a) * r}`;
  }).join(" ");
}

const HeroSvgFallback: FC = () => (
  <div
    data-testid="hero-illustration"
    className="pointer-events-none aspect-square w-full max-w-[520px]"
    style={{ color: "var(--abs-brand)" }}
  >
    <svg
      viewBox="0 0 320 320"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Six providers cascading into a self-hosted vault"
      className="h-full w-full"
      fill="none"
    >
      {nodes.map((n, i) => (
        <line
          key={`spoke-${i}`}
          x1={n.x}
          y1={n.y}
          x2={CENTER}
          y2={CENTER}
          stroke="currentColor"
          strokeWidth="1"
          opacity="0.16"
        />
      ))}

      <polygon
        points={hexPoints(70)}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <polygon
        points={hexPoints(46)}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        opacity="0.22"
      />
      <circle cx={CENTER} cy={CENTER} r="14" fill="currentColor" />

      {nodes.map((n, i) => (
        <circle key={`node-${i}`} cx={n.x} cy={n.y} r="5.5" fill="currentColor" opacity="0.7" />
      ))}
    </svg>
  </div>
);

export default HeroSvgFallback;
