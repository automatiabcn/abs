// T-R03 — ABS-branded logo mark. Two concentric arcs + central spark.
// Inherits `currentColor`; sized via `width`/`height` props.
import type { SVGProps } from "react";

export default function AbsLogo({ size = 32, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      role="img"
      aria-label="ABS Server"
      {...rest}
    >
      <circle cx="16" cy="16" r="13" opacity="0.35" />
      <path d="M16 3 a13 13 0 0 1 13 13" />
      <circle cx="16" cy="16" r="3" fill="currentColor" stroke="none" />
    </svg>
  );
}
