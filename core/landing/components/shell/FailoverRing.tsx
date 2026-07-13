/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The failover ring — the product's signature mark, drawn from live data.
//
// The landing page sells "one provider falls, the next takes over" with a 3D
// version of this exact figure; the panel keeps the promise with ~1KB of SVG:
// one node per provider around a rotating beam, green when standing, muted
// when not. Marketing animation and product telemetry speak the same visual
// language, which is the point — deliberately no WebGL here. An operator's
// status strip must cost nothing.
"use client";

interface FailoverRingProps {
  up: number | null;
  total: number | null;
  size?: number;
}

export function FailoverRing({ up, total, size = 26 }: FailoverRingProps) {
  // Unknown state renders the idle geometry — never a false alarm.
  const n = Math.min(Math.max(total ?? 6, 3), 8);
  const upCount = up ?? n;

  const nodes = Array.from({ length: n }, (_, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    return {
      x: 16 + 10.5 * Math.cos(angle),
      y: 16 + 10.5 * Math.sin(angle),
      healthy: i < upCount,
    };
  });

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle cx="16" cy="16" r="10.5" fill="none" stroke="var(--abs-border)" strokeWidth="1" />
      <circle
        className="abs-ring-beam"
        cx="16"
        cy="16"
        r="10.5"
        fill="none"
        stroke="var(--abs-brand)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle className="abs-ring-core" cx="16" cy="16" r="4.4" fill="var(--abs-brand)" opacity="0.9" />
      {nodes.map((node, i) => (
        <circle
          key={i}
          cx={node.x}
          cy={node.y}
          r={node.healthy ? 2.4 : 2}
          fill={node.healthy ? "var(--abs-success)" : "var(--abs-fg-subtle)"}
        />
      ))}
    </svg>
  );
}
