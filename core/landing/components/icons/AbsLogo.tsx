/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The vault: a closed box with the core held inside it.
//
// This replaces a generic "AI swirl" that could have belonged to any model
// wrapper on the market and said nothing about what the product is. The mark
// carries the one promise the product actually makes — your data sits in a
// box you own — and keeps continuity with the Automatia BCN isometric cube
// instead of discarding the parent brand.
//
// The shell inherits `currentColor` so it reads on any surface; the core is
// the brand token, the single point of colour in the mark. It survives down
// to 16px, where the old swirl collapsed into a smudge of light.
import type { SVGProps } from "react";

export default function AbsLogo({
  size = 32,
  ...rest
}: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      role="img"
      aria-label="Automatia ABS"
      {...rest}
    >
      <path
        d="M24 5 L41 14 L41 34 L24 43 L7 34 L7 14 Z"
        stroke="currentColor"
        strokeWidth="3.4"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="24" r="6" fill="var(--abs-brand)" />
    </svg>
  );
}
