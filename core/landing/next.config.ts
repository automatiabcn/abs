import type { NextConfig } from "next";
import withBundleAnalyzer from "@next/bundle-analyzer";

// T-R03 fix #2 — `ANALYZE=true npm run build` writes .next/analyze/*.html
// reports we can ship to the QA artifacts dir.
const enableAnalyzer = withBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
  openAnalyzer: false,
});

/**
 * 024 — Security headers for Lighthouse best-practices ≥ 100.
 *
 * - X-Content-Type-Options: nosniff   — prevent MIME sniffing
 * - X-Frame-Options: DENY              — clickjacking protection
 * - Referrer-Policy: strict-origin-when-cross-origin
 * - Permissions-Policy: minimal allowlist
 * - Strict-Transport-Security: HSTS (production only — Caddy/Vercel adds in HTTP)
 * - Content-Security-Policy: tight allowlist for self + Stripe + Loom embeds
 */
// T-R03 revise — dev mode adds `'unsafe-eval'` so React Refresh + Framer Motion
// runtime can hydrate. Production CSP is unchanged (strict).
const IS_DEV = process.env.NODE_ENV !== "production";

const SCRIPT_SRC = [
  "'self'",
  "'unsafe-inline'",
  ...(IS_DEV ? ["'unsafe-eval'"] : []),
  "https://js.stripe.com",
].join(" ");

const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `script-src ${SCRIPT_SRC}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      "frame-src https://www.loom.com https://js.stripe.com https://billing.stripe.com",
      "connect-src 'self' https://api.stripe.com",
      "frame-ancestors 'self'",
      "form-action 'self' https://checkout.stripe.com",
    ].join("; "),
  },
];

// Q6 PB — same-origin proxy to the FastAPI backend so panel pages can
// `fetch("/v1/meetings")` without CORS / cookie-domain pain. Override with
// ABS_BACKEND_URL when the backend is on a different host (Docker, prod).
const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // T-Q06 — emit standalone server output so the multi-stage Dockerfile can
  // ship a minimal runtime image (`node server.js`).
  output: "standalone",
  // T-Q06 — silence the multi-lockfile root-inference warning seen in dev.
  outputFileTracingRoot: __dirname,
  async rewrites() {
    return [
      { source: "/v1/:path*", destination: `${BACKEND_URL}/v1/:path*` },
      { source: "/auth/login", destination: `${BACKEND_URL}/auth/login` },
      { source: "/auth/logout", destination: `${BACKEND_URL}/auth/logout` },
      { source: "/auth/me", destination: `${BACKEND_URL}/auth/me` },
      { source: "/auth/signup", destination: `${BACKEND_URL}/auth/signup` },
      // /auth/magic — frontend page exists, but its GET handler also needs
      // backend reach for token claim. Both are at /auth/magic so the
      // rewrite would shadow the page; instead the magic page calls
      // /auth/magic via fetch which is rewritten path-wise too. Skip the
      // top-level /auth/magic rewrite to keep the page functional.
      { source: "/healthz", destination: `${BACKEND_URL}/healthz` },
      { source: "/openapi.json", destination: `${BACKEND_URL}/openapi.json` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default enableAnalyzer(nextConfig);
