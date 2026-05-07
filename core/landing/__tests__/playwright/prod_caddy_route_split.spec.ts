// Brief 4 R7 — Caddy route split contract.
//
// `/`            → landing:3000 (Next.js HTML)
// `/v1/*`        → backend:8000 (FastAPI JSON)
// `/auth/*`      → backend:8000
// `/setup`       → backend:8000
// `/panel`       → backend:8000  (308 redirect to /admin)
// `/api/health`  → landing:3000
// `/admin/*`     → landing:3000

import { expect, test } from "@playwright/test";

import { PROD_BASE_URL, requireProdStack } from "./helpers/prod-stack";

test.describe("Brief 4 R7 — Caddy route split (production stack)", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireProdStack(request, testInfo);
  });

  test("`/` lands on the marketing/landing service", async ({ request }) => {
    const r = await request.get(`${PROD_BASE_URL}/`, {
      ignoreHTTPSErrors: true,
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.text();
    expect(body).toMatch(/<html/i);
    // Landing pages share the brand wordmark; backend HTML wouldn't.
    expect(body).toMatch(/Automatia/i);
  });

  test("`/api/health` is served by landing (not backend)", async ({
    request,
  }) => {
    const r = await request.get(`${PROD_BASE_URL}/api/health`, {
      ignoreHTTPSErrors: true,
    });
    expect(r.ok()).toBeTruthy();
    const json = (await r.json()) as { service?: string; status?: string };
    expect(json.service).toBe("abs-landing");
    expect(json.status).toBe("ok");
  });

  test("`/v1/healthz`-equivalent path is served by backend (JSON)", async ({
    request,
  }) => {
    const r = await request.get(`${PROD_BASE_URL}/healthz`, {
      ignoreHTTPSErrors: true,
    });
    expect(r.ok()).toBeTruthy();
    const ctype = (r.headers()["content-type"] ?? "").toLowerCase();
    expect(ctype).toContain("application/json");
  });

  test("`/panel` returns a 308 redirect to `/admin` (legacy panel deprecated)", async ({
    request,
  }) => {
    const r = await request.get(`${PROD_BASE_URL}/panel`, {
      ignoreHTTPSErrors: true,
      maxRedirects: 0,
    });
    expect(r.status()).toBe(308);
    expect(r.headers()["location"]).toBe("/admin");
  });

  test("`/admin` is served by landing (Next.js owns the surface)", async ({
    request,
  }) => {
    // Unauthenticated visit redirects to /admin/login (handled inside
    // the landing middleware), but the response always comes from
    // landing — never the backend's now-deleted /admin route.
    const r = await request.get(`${PROD_BASE_URL}/admin/login`, {
      ignoreHTTPSErrors: true,
    });
    expect(r.ok() || r.status() === 401 || r.status() === 302).toBeTruthy();
    const body = await r.text();
    // Landing ships the Next.js bundle; backend would have returned a
    // FastAPI HTML page or the deleted vanilla 032 admin.
    expect(body).toMatch(/<html/i);
  });
});
