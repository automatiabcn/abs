// Brief 4 R7 — shared helpers for the production-like Playwright
// suites (`prod_*.spec.ts`). The specs exercise the running compose
// stack (Caddy + landing + backend), so they need a different base URL
// from the default `next dev` flow.
//
// Usage:
//
//   docker compose -f infra/docker-compose.yml up -d
//   PLAYWRIGHT_BASE_URL=https://abs.local \
//     PLAYWRIGHT_PROD_STACK=1 \
//     npx playwright test prod_
//
// When `PLAYWRIGHT_PROD_STACK` is unset (the default `next dev` flow),
// each prod_* suite calls `requireProdStack()` in its beforeAll hook
// to skip — these tests never assert against the dev server.

import type { APIRequestContext, TestInfo } from "@playwright/test";

export const PROD_BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL ?? "https://abs.local";

export const PROD_STACK_FLAG =
  (process.env.PLAYWRIGHT_PROD_STACK ?? "").toLowerCase() === "1" ||
  (process.env.PLAYWRIGHT_PROD_STACK ?? "").toLowerCase() === "true";

export const ADMIN_EMAIL =
  process.env.ABS_ADMIN_EMAIL ?? "admin@local";
export const ADMIN_PASSWORD =
  process.env.ABS_ADMIN_PASSWORD ?? "CHANGEME";

export const COOKIE_NAME = "abs_session";

/**
 * Skip the calling suite when the compose stack is not flagged on or
 * the landing healthcheck doesn't answer. Mirrors the brief's
 * "production-like flow" intent without breaking the default
 * `npx playwright test` invocation.
 */
export async function requireProdStack(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<void> {
  if (!PROD_STACK_FLAG) {
    testInfo.skip(
      true,
      "Brief 4 R7: set PLAYWRIGHT_PROD_STACK=1 to run prod_* suites against the running compose stack.",
    );
    return;
  }
  try {
    const res = await request.get(`${PROD_BASE_URL}/api/health`, {
      ignoreHTTPSErrors: true,
    });
    if (!res.ok()) {
      testInfo.skip(true, `landing /api/health returned ${res.status()}`);
    }
  } catch (exc) {
    testInfo.skip(true, `compose stack not reachable: ${String(exc)}`);
  }
}

/**
 * POST /auth/login through Caddy and return the freshly-set session
 * cookie. Used by every spec that needs to land inside `/admin/*`.
 */
export async function loginThroughCaddy(
  request: APIRequestContext,
): Promise<{ name: string; value: string }> {
  const res = await request.post(`${PROD_BASE_URL}/auth/login`, {
    ignoreHTTPSErrors: true,
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  if (!res.ok()) {
    throw new Error(`/auth/login failed: ${res.status()} ${await res.text()}`);
  }
  const setCookie =
    res.headers()["set-cookie"] ?? res.headers()["Set-Cookie"] ?? "";
  const match = setCookie.match(
    new RegExp(`${COOKIE_NAME}=([^;]+)`),
  );
  if (!match) {
    throw new Error(
      `Set-Cookie did not include ${COOKIE_NAME}; raw=${setCookie}`,
    );
  }
  return { name: COOKIE_NAME, value: match[1] };
}
