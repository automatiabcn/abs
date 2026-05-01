// T-R03 — RAG document + vector glyph.
import type { SVGProps } from "react";

export default function AbsRag({ size = 32, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
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
      aria-label="Retrieval-augmented generation"
      {...rest}
    >
      <path d="M9 4 L21 4 L26 9 L26 28 L9 28 Z" />
      <path d="M21 4 L21 9 L26 9" />
      <line x1="13" y1="14" x2="22" y2="14" />
      <line x1="13" y1="18" x2="20" y2="18" />
      <line x1="13" y1="22" x2="22" y2="22" />
      <circle cx="6" cy="14" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="6" cy="18" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="6" cy="22" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  );
}
