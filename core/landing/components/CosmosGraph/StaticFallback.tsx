/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Brief 2 R4 — `prefers-reduced-motion` static fallback.
//
// Renders an iso-axonometric SVG layout (Variant 3 reference from
// `MOCKUP_GATE.md`) instead of the WebGL force graph. No physics, no
// animation, no GPU work — same provider list, same single brand
// palette, same a11y labels. The element is keyboard-navigable: each
// provider is a `<button>` with `role="button" aria-label="..."`.

"use client";

import { PALETTE } from "./colors";

interface Props {
  height?: number;
  highlightProvider?: string;
  /** The providers this server actually has. Was a hardcoded list of seven. */
  providers?: string[];
}

export function CosmosStaticFallback({
  height = 420,
  highlightProvider,
  providers = [],
}: Props) {
  const cols = 4;
  const cellW = 160;
  const cellH = 80;
  const top = 60;
  const left = 60;

  return (
    <div
      data-testid="cosmos-fallback"
      data-test="cosmos-fallback"
      className="w-full overflow-hidden rounded-xl border border-border bg-background/60"
      style={{ height, background: PALETTE.bg }}
      role="group"
      aria-label="ABS provider grid (reduced-motion view)"
    >
      <svg
        viewBox={`0 0 ${left * 2 + cellW * cols} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-hidden="false"
      >
        {/* hairline grid */}
        <g stroke={PALETTE.edge} strokeWidth="1">
          {Array.from({ length: 5 }).map((_, i) => (
            <line
              key={`h${i}`}
              x1={0}
              y1={top + i * 60}
              x2={left * 2 + cellW * cols}
              y2={top + i * 60}
            />
          ))}
        </g>
        {providers.map((name, i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          const x = left + col * cellW + 20;
          const y = top + row * cellH + 30;
          const isActive = !!highlightProvider && name === highlightProvider;
          return (
            <g key={name}>
              <rect
                x={x}
                y={y}
                width={cellW - 40}
                height={cellH - 30}
                rx="10"
                fill={
                  isActive
                    ? PALETTE.highlight
                    : "rgba(30, 87, 172, 0.55)"
                }
                stroke={PALETTE.accent}
                strokeWidth={isActive ? 2 : 1}
                role="button"
                tabIndex={0}
                aria-label={`${name} provider, status: ${
                  isActive ? "active" : "configured"
                }`}
              />
              <text
                x={x + (cellW - 40) / 2}
                y={y + (cellH - 30) / 2 + 4}
                textAnchor="middle"
                fill={PALETTE.textBright}
                fontSize="14"
                fontFamily="ui-sans-serif, system-ui"
                pointerEvents="none"
              >
                {name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default CosmosStaticFallback;
