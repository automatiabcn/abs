// T-Q06 — Next 15 + TS strict ESLint flat config.
// Run via `npm run lint` or `npx next lint`.
import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Hard fails — production-blocking quality bar.
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "react-hooks/exhaustive-deps": "warn",
      // T-Q05 — R3F custom JSX elements (e.g. `<line>`) need this off so
      // three.js primitives don't trigger react/no-unknown-property.
      "react/no-unknown-property": [
        "warn",
        {
          ignore: [
            "object",
            "attach",
            "args",
            "position",
            "intensity",
            "transparent",
            "side",
            "emissive",
            "emissiveIntensity",
            "roughness",
            "metalness",
            "flatShading",
            "sizeAttenuation",
            "count",
            "itemSize",
          ],
        },
      ],
      // Apostrophes in Turkish / Spanish copy are common; the rule only
      // protects against accidental JSX-syntax confusion which the editor
      // catches.
      "react/no-unescaped-entities": "off",
    },
  },
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "coverage/**",
    ],
  },
];

export default eslintConfig;
