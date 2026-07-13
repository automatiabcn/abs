// P1 — E2 / X4: connecting somebody else's MCP server, and surviving it.
//
// This is the feature that lets a company plug its own systems into ABS. It is
// also the feature that hands a third party a foothold, so the interesting
// questions are not "does the happy path work" but:
//
//   E2  — connect, discover, and see the tools show up in the catalogue.
//   X4  — the server dies afterwards. The panel must not fall over, the failure
//         must be legible, and a tool that cannot run must not sit in the
//         catalogue pretending it can.
//   And: a URL pointing at the machine's own guts is refused before it is dialled.
//
// The "remote" server used here is this backend's own /mcp endpoint. That is a
// real MCP server speaking the real protocol over a real socket — a stub would
// only prove the stub works.

import { expect, test } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

const BACKEND = process.env.ABS_BACKEND_URL ?? "http://127.0.0.1:8000";

// Registered servers are rows. A fresh name per run, and a cleanup that runs
// even when an assertion fails, or the next run tests the duplicate path by
// accident.
const LIVE = `scenario-live-${Date.now()}`;
const DEAD = `scenario-dead-${Date.now()}`;
const slugs: string[] = [];

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test.afterAll(async ({ request }) => {
  for (const slug of slugs) {
    await request.delete(`/v1/admin/external-mcp/${slug}`, {
      failOnStatusCode: false,
    });
  }
});

test("E2 — connect a server, and its tools arrive in the catalogue", async ({
  request,
}) => {
  // A real MCP server needs a real credential. Mint one the way the Access Keys
  // page does, and hand it over the way an operator pastes a colleague's token —
  // so this exercises the bearer path, not just the happy unauthenticated one.
  const minted = await request.post("/v1/mcp/tokens", {
    data: { label: `scenario-extmcp-${Date.now()}`, scope: "mcp", days: 1 },
    headers: { "Content-Type": "application/json" },
  });
  expect(minted.status(), await minted.text()).toBe(201);
  const token: string = (await minted.json()).token;

  const created = await request.post("/v1/admin/external-mcp", {
    data: {
      name: LIVE,
      // Trailing slash on purpose: /mcp answers 307 to /mcp/, and the MCP
      // transport does not follow it. That is a real trap for a customer typing
      // their own server's address — see the error-message assertion in X4.
      url: `${BACKEND}/mcp/`,
      transport: "http",
      auth_type: "bearer",
      secret: token,
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const server = await created.json();
  slugs.push(server.slug);

  // Registering does not dial it. A server you have merely typed in is not a
  // server you have connected, and the panel must not imply otherwise.
  expect(server.status).toBe("unconfigured");
  expect(server.discovered_tool_count).toBe(0);

  // The secret never comes back, and there is no field where it could hide.
  expect(JSON.stringify(server)).not.toMatch(/secret|password|bearer /i);

  // Now dial it — this is the button the operator presses.
  const tested = await request.post(`/v1/admin/external-mcp/${server.slug}/test`);
  expect(tested.status(), await tested.text()).toBe(200);
  const result = await tested.json();

  expect(result.ok, `connect failed: ${JSON.stringify(result)}`).toBe(true);
  expect(
    result.tool_count,
    "the server connected and offered no tools — nothing was actually discovered",
  ).toBeGreaterThan(0);
  expect(Array.isArray(result.tools)).toBe(true);
  expect(result.tools[0]).toHaveProperty("name");

  // And the row now says so, so the next person to open the page sees it too.
  const row = await request.get(`/v1/admin/external-mcp/${server.slug}`);
  const saved = await row.json();
  expect(saved.status).toBe("ok");
  expect(saved.discovered_tool_count).toBeGreaterThan(0);
  expect(saved.last_checked_at).toBeTruthy();
});

test("X4 — a server that cannot be reached fails legibly, and poisons nothing", async ({
  request,
}) => {
  // Port 1 with nothing on it: the shape of a colleague's laptop that went to
  // sleep, or a container that stopped.
  const created = await request.post("/v1/admin/external-mcp", {
    data: {
      name: DEAD,
      url: "http://127.0.0.1:1/mcp",
      transport: "http",
      auth_type: "none",
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const server = await created.json();
  slugs.push(server.slug);

  const tested = await request.post(`/v1/admin/external-mcp/${server.slug}/test`);

  // 200 with ok:false, not a 5xx. An operator pressing "test" on a dead server
  // must be told the server is dead — a stack trace tells them their own panel
  // is broken, which is the one thing this button exists to rule out.
  expect(
    tested.status(),
    "testing a dead server crashed the endpoint instead of reporting the failure",
  ).toBe(200);
  const result = await tested.json();
  expect(result.ok).toBe(false);
  expect(result.tool_count ?? 0).toBe(0);

  // And it says something the operator can act on. This used to read
  // "ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)" — the
  // MCP transports run inside an anyio task group, so every real cause arrived
  // wrapped, and the panel printed the wrapper. Non-empty is not the bar; a
  // person who has just pasted a URL and pressed a button has to learn something.
  const error = String(result.error ?? "");
  expect(error, "it failed and said nothing").not.toBe("");
  expect(
    error,
    `the operator is shown the plumbing instead of the problem: ${error}`,
  ).not.toMatch(/TaskGroup|sub-exception/);
  expect(
    error,
    `nothing in this names the actual failure: ${error}`,
  ).toMatch(/refus|connect|timeout|unreachable|Errno/i);

  // The failure is remembered, so the page shows it without re-dialling.
  const row = await request.get(`/v1/admin/external-mcp/${server.slug}`);
  const saved = await row.json();
  expect(saved.status).toBe("error");
  expect(saved.last_error).toBeTruthy();
  expect(saved.discovered_tool_count).toBe(0);

  // Nothing from a server that never answered may appear in the tool catalogue.
  // A tool listed there is a tool the assistant will try to call.
  const cat = await request.get("/v1/panel/tools");
  expect(cat.status()).toBe(200);
  const { tools } = await cat.json();
  const ghosts = tools.filter((t: { name: string }) =>
    t.name.startsWith(`ext_${server.slug}__`),
  );
  expect(
    ghosts,
    "a server that has never once answered contributed tools to the catalogue",
  ).toEqual([]);
});

test("E2 — the panel lists both, and tells them apart", async ({ request }) => {
  const resp = await request.get("/v1/admin/external-mcp");
  expect(resp.status()).toBe(200);
  const { servers } = await resp.json();

  const live = servers.find((s: { name: string }) => s.name === LIVE);
  const dead = servers.find((s: { name: string }) => s.name === DEAD);

  expect(live, "the connected server is missing from the list").toBeTruthy();
  expect(dead, "the broken server is missing from the list").toBeTruthy();
  expect(live.status).toBe("ok");
  expect(dead.status).toBe("error");

  // No secrets in the list view either — this is the response the browser gets.
  expect(await resp.text()).not.toMatch(/gsk_|sk-|Bearer /);
});

test("E2 — a URL aimed at the server's own insides is refused before it is dialled", async ({
  request,
}) => {
  // The classic shape of this attack: an operator is talked into adding a
  // "server" whose URL is a cloud metadata endpoint, and ABS — which can reach
  // it and they cannot — fetches the instance credentials on their behalf.
  const resp = await request.post("/v1/admin/external-mcp", {
    data: {
      name: `scenario-ssrf-${Date.now()}`,
      url: "http://169.254.169.254/latest/meta-data/",
      transport: "http",
      auth_type: "none",
    },
    failOnStatusCode: false,
  });

  expect(
    resp.status(),
    "the link-local metadata address was accepted as an MCP server",
  ).toBe(422);
  expect(await resp.text()).toMatch(/blocked_internal_address/);
});
