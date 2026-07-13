import type { Config } from "tailwindcss";

/**
 * Colour keys resolve to the channel triples declared in app/tokens.css, with
 * `<alpha-value>` left in place so opacity modifiers keep working — the panel
 * leans on ~190 of them (`bg-card/60`, `border-primary/50`) and a colour handed
 * over as a finished `var(--x)` string would have quietly rendered none of them.
 *
 * Two bugs died here:
 *
 * - `destructive`, `secondary` and `accent` were never defined, so three of the
 *   Button component's six variants emitted class names Tailwind had no rule
 *   for. Twenty-five call sites rendered unstyled and nothing failed.
 * - `sans` named Inter, which no font loader ever loaded, so body text fell back
 *   to system-ui while Geist — which *is* loaded — only reached headings.
 */
const rgb = (name: string) => `rgb(var(--abs-${name}-rgb) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        canvas: rgb("canvas"),
        background: rgb("canvas"),
        foreground: rgb("fg"),

        card: {
          DEFAULT: rgb("surface"),
          foreground: rgb("fg"),
        },
        surface: {
          DEFAULT: rgb("surface"),
          raised: rgb("surface-raised"),
          sunken: rgb("surface-sunken"),
        },

        primary: {
          DEFAULT: rgb("brand"),
          hover: rgb("brand-hover"),
          soft: rgb("brand-soft"),
          foreground: rgb("brand-fg"),
        },
        secondary: {
          DEFAULT: rgb("surface-raised"),
          foreground: rgb("fg"),
        },
        accent: {
          DEFAULT: rgb("surface-raised"),
          foreground: rgb("fg"),
        },
        muted: {
          DEFAULT: rgb("surface-raised"),
          foreground: rgb("fg-muted"),
        },
        subtle: rgb("fg-subtle"),

        destructive: {
          DEFAULT: rgb("danger"),
          soft: rgb("danger-soft"),
          foreground: rgb("danger-fg"),
        },
        success: {
          DEFAULT: rgb("success"),
          soft: rgb("success-soft"),
        },
        warning: {
          DEFAULT: rgb("warning"),
          soft: rgb("warning-soft"),
        },
        info: {
          DEFAULT: rgb("info"),
          soft: rgb("info-soft"),
        },

        border: {
          DEFAULT: rgb("border"),
          soft: rgb("border-soft"),
          strong: rgb("border-strong"),
        },
        input: rgb("border"),
        ring: rgb("ring"),
      },
      borderRadius: {
        sm: "var(--abs-radius-sm)",
        DEFAULT: "var(--abs-radius)",
        md: "var(--abs-radius)",
        lg: "var(--abs-radius-lg)",
      },
      boxShadow: {
        sm: "var(--abs-shadow-sm)",
        DEFAULT: "var(--abs-shadow-md)",
        md: "var(--abs-shadow-md)",
        lg: "var(--abs-shadow-lg)",
      },
    },
  },
  plugins: [],
};

export default config;
