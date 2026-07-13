// P1 — E3: an access key can be issued, used, and killed.
//
// This is the key a customer pastes into Claude Code, an editor, a script on a
// laptop. It is the credential most likely to end up somewhere it should not:
// a screenshot, a shared repo, a colleague who left. Revocation is the whole
// security story of that surface, and a revoke that takes effect "soon" is not
// a revoke — the window between the operator clicking the button and the key
// going dead is exactly the window an attacker is in.
//
// So the test does not check that the button returns 204. It checks that the
// key worked, then that the same request with the same key fails, immediately,
// on the next call — no waiting, no cache to expire.

import { expect, test } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("E3 — an access key works, and the moment it is revoked it does not", async ({
  request,
}) => {
  // Issue one, the way the Access Keys page does.
  const minted = await request.post("/v1/mcp/tokens", {
    data: { label: `scenario-${Date.now()}`, scope: "mcp", days: 1 },
    headers: { "Content-Type": "application/json" },
  });
  expect(minted.status(), await minted.text()).toBe(201);
  const token: string = (await minted.json()).token;
  expect(token.startsWith("abs_mcp_"), "not an access key").toBe(true);

  // It works. Proving this first is the point: a test that only checks the
  // revoke would pass just as happily against a key that never worked at all.
  const before = await request.get("/v1/mcp/tokens/verify", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(before.status(), await before.text()).toBe(200);
  expect((await before.json()).ok).toBe(true);

  // Kill it.
  const revoked = await request.post("/v1/mcp/tokens/revoke", {
    data: { token },
    headers: { "Content-Type": "application/json" },
  });
  expect([200, 204]).toContain(revoked.status());

  // And it is dead on the very next call — not after a cache, not after a
  // heartbeat, not on the next tick of anything.
  const after = await request.get("/v1/mcp/tokens/verify", {
    headers: { Authorization: `Bearer ${token}` },
    failOnStatusCode: false,
  });
  expect(
    after.status(),
    "a revoked key still authenticated — the revoke button is decoration",
  ).toBe(401);

  // Revoking twice is not an error. An operator who panics and clicks again
  // must not be told something went wrong.
  const again = await request.post("/v1/mcp/tokens/revoke", {
    data: { token },
    headers: { "Content-Type": "application/json" },
    failOnStatusCode: false,
  });
  expect([200, 204]).toContain(again.status());
});

test("E3b — a forged key is refused, and so is a key with no signature", async ({
  request,
}) => {
  // The tokens are self-describing: prefix, body, signature. Anyone can read
  // the body and write their own — the signature is the only thing standing
  // between a curious customer and every tool on the server.
  const minted = await request.post("/v1/mcp/tokens", {
    data: { label: `forge-${Date.now()}`, scope: "mcp", days: 1 },
    headers: { "Content-Type": "application/json" },
  });
  expect(minted.status()).toBe(201);
  const token: string = (await minted.json()).token;

  // Same token, one character of the signature changed.
  const sig = token.slice(-1) === "A" ? "B" : "A";
  const forged = token.slice(0, -1) + sig;

  const forgedResp = await request.get("/v1/mcp/tokens/verify", {
    headers: { Authorization: `Bearer ${forged}` },
    failOnStatusCode: false,
  });
  expect(forgedResp.status(), "a tampered signature was accepted").toBe(401);

  // And the body without a signature at all.
  const unsigned = await request.get("/v1/mcp/tokens/verify", {
    headers: { Authorization: `Bearer ${token.split(".")[0]}` },
    failOnStatusCode: false,
  });
  expect(unsigned.status(), "an unsigned key was accepted").toBe(401);
});
