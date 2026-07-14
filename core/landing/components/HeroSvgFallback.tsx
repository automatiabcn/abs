/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// 2D SVG fallback for mobile / tablet / reduced-motion users.
// Lifted from the original Hero illustration; isometric cube stack in brand colors.
import type { FC } from "react";

const HeroSvgFallback: FC = () => (
  <div
    data-testid="hero-illustration"
    className="pointer-events-none absolute inset-0 -z-10 flex items-center justify-center opacity-60"
  >
    <svg
      viewBox="0 0 400 360"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Self-host AI orchestration illustration"
      className="h-auto w-full max-w-md"
    >
      <defs>
        <linearGradient id="brandTopFb" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1e57ac" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
        <linearGradient id="brandLeftFb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e57ac" />
          <stop offset="100%" stopColor="#0f3a78" />
        </linearGradient>
        <linearGradient id="brandRightFb" x1="1" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#1e3a8a" />
        </linearGradient>
      </defs>
      <g>
        <polygon points="200,260 320,200 320,320 200,360" fill="url(#brandRightFb)" />
        <polygon points="80,200 200,260 200,360 80,300" fill="url(#brandLeftFb)" />
        <polygon points="80,200 200,140 320,200 200,260" fill="url(#brandTopFb)" />
      </g>
      <g opacity="0.92" transform="translate(0,-90)">
        <polygon points="200,260 280,220 280,300 200,340" fill="url(#brandRightFb)" />
        <polygon points="120,220 200,260 200,340 120,300" fill="url(#brandLeftFb)" />
        <polygon points="120,220 200,180 280,220 200,260" fill="url(#brandTopFb)" />
      </g>
      <g opacity="0.85" transform="translate(0,-180)">
        <polygon points="200,250 250,225 250,290 200,315" fill="url(#brandRightFb)" />
        <polygon points="150,225 200,250 200,315 150,290" fill="url(#brandLeftFb)" />
        <polygon points="150,225 200,200 250,225 200,250" fill="url(#brandTopFb)" />
      </g>
      <circle cx="60" cy="80" r="4" fill="#3b82f6" opacity="0.5" />
      <circle cx="350" cy="60" r="3" fill="#3b82f6" opacity="0.4" />
      <circle cx="380" cy="270" r="3" fill="#3b82f6" opacity="0.5" />
    </svg>
  </div>
);

export default HeroSvgFallback;
