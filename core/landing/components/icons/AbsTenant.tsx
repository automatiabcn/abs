// T-R03 — multi-tenant isolation glyph: 3 stacked workspace cards with shield.
import type { SVGProps } from "react";

export default function AbsTenant({ size = 32, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinejoin="round"
      role="img"
      aria-label="Multi-tenant isolation"
      {...rest}
    >
      <rect x="4" y="6" width="20" height="14" rx="2" opacity="0.45" />
      <rect x="6" y="9" width="20" height="14" rx="2" opacity="0.7" />
      <rect x="8" y="12" width="20" height="14" rx="2" />
      <path
        d="M18 17 L18 21 C18 22 19 23 19 23 L21 23 C21 23 22 22 22 21 L22 17 Z"
        fill="currentColor"
        stroke="none"
        opacity="0.85"
      />
    </svg>
  );
}
