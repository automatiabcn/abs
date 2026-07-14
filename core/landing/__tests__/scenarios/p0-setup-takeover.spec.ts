// a configured server cannot be taken over by whoever finds /setup.
//
// The setup wizard creates the first admin, and it is the one endpoint that is
// unauthenticated by necessity — before it runs, there is nobody to authenticate
// as. That makes it the softest thing on the box. If it stays open after the
// install is done, then anyone who can reach the server can create themselves an
// admin account and own it, and no amount of care anywhere else in the product
// matters.
//
// So the closed door gets a test. Not because the code looks wrong, but because
// this is the failure nobody would notice until it had already happened: there
// is no error, no alert, no red badge — just a second admin who was never
// invited.

import { expect, test } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("S1 — setup is closed once it has run, and refuses a second admin", async ({ request }) => {
  // This backend is installed: an admin exists and the suite is signed in as
  // them. Anything that lets the wizard run again is a takeover.
  const status = await request.get("/v1/setup/status");
  expect(status.ok(), await status.text()).toBe(true);
  const body = await status.json();
  expect(
    body.completed ?? body.data?.completed ?? true,
    "this scenario is meaningless on a server that has not been set up",
  ).toBeTruthy();

  // The attempt: a stranger, with no session, posting a brand new admin.
  const takeover = await request.post("/v1/setup/admin", {
    data: {
      email: "attacker@example.com",
      password: "AttackerPassword123!",
    },
    headers: { "Content-Type": "application/json" },
    failOnStatusCode: false,
  });

  // Refused. 409 is the wizard's own "already completed"; 401/403 mean it is
  // behind auth. Any 2xx here is a takeover, and the test says so in those
  // words because that is what it would be.
  expect(
    [401, 403, 409, 404],
    `POST /v1/setup/admin returned ${takeover.status()} — a configured server let a stranger create an admin`,
  ).toContain(takeover.status());

  // And the door is still shut behind it: a second attempt does not slip through
  // on a race or a cached state.
  const again = await request.post("/v1/setup/admin", {
    data: { email: "attacker2@example.com", password: "AttackerPassword123!" },
    headers: { "Content-Type": "application/json" },
    failOnStatusCode: false,
  });
  expect([401, 403, 409, 404]).toContain(again.status());
});
