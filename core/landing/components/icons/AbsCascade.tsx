/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Represents the 6-provider AI cascade as a radial fan.
import type { SVGProps } from "react";

export default function AbsCascade({ size = 32, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      role="img"
      aria-label="6-provider AI cascade"
      {...rest}
    >
      <circle cx="16" cy="26" r="2.5" fill="currentColor" stroke="none" />
      {[-2, -1, 0, 1, 2, 3].map((k, i) => (
        <line
          key={i}
          x1="16"
          y1="26"
          x2={16 + k * 5}
          y2={6 + Math.abs(k) * 1.2}
        />
      ))}
      <circle cx="6" cy="9.4" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="11" cy="7.2" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="16" cy="6" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="21" cy="7.2" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="26" cy="9.4" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="31" cy="12.6" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}
