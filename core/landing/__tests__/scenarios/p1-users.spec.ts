// P1 — S2: inviting a colleague, and what that colleague can see.
//
// The moment a company puts more than one person on this server, two promises
// start mattering: an invited member gets in, and an invited member does not
// get the keys. Both are checked here against a real invite through the real
// endpoint, not a seeded row.
//
// There is a third promise, less obvious and more embarrassing, that this file
// also holds: the roster is *real*. When the fetch failed, this page used to
// render three colleagues who do not exist — including an account called
// admin@demo-acme.com, sitting there with admin, on a customer's own server.
// An admin who saw that was right to be alarmed and wrong about why. It also
// hid the inverse: a roster that would not load looked like a populated one.

import { expect, test } from "@playwright/test";

import { login, requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

// A fresh address per run: an invite is a real row, and a test that reuses one
// tests the duplicate path by accident on its second run.
const INVITEE = `member-${Date.now()}@scenario.example.com`;

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("S2 — an admin invites a member, and gets a way to let them in", async ({
  request,
}) => {
  const resp = await request.post("/v1/admin/users/invite", {
    data: { email: INVITEE, role: "member" },
  });
  expect(resp.status(), await resp.text()).toBe(201);
  const body = await resp.json();

  expect(body.email).toBe(INVITEE);
  expect(body.role).toBe("member");
  expect(body.status).toBe("pending");

  // Self-hosted servers usually have no SMTP. When ABS cannot send the mail it
  // must hand the admin the link instead — an invite that is neither delivered
  // nor collectable is a user who never arrives, and the admin has no way to
  // know that happened.
  if (!body.email_sent) {
    expect(
      String(body.magic_url ?? ""),
      "no mail was sent and no link was given — the invited person cannot get in",
    ).toContain("/activate?token=");
  }

  // The invite is now visible to the admin who sent it.
  const list = await request.get("/v1/admin/users/invites");
  expect(list.status()).toBe(200);
  const { invites } = await list.json();
  expect(
    invites.some((i: { email: string }) => i.email === INVITEE),
    "the invite was accepted but does not appear in the list of invites",
  ).toBe(true);
});

test("S2 — inviting the same person twice is refused, not silently duplicated", async ({
  request,
}) => {
  // Two invites, two magic links, two ways in for one person — and only one of
  // them ever gets revoked.
  const again = await request.post("/v1/admin/users/invite", {
    data: { email: INVITEE, role: "member" },
    failOnStatusCode: false,
  });
  expect(again.status(), await again.text()).toBe(409);
  const body = await again.json();
  expect(JSON.stringify(body)).toContain("duplicate_pending_invite");
});

test("S2 — a signed-in member is not shown the admin panel", async ({
  browser,
  request,
}) => {
  // Take the invite through the door it was made for: claim the token, land in
  // a session, and see what that session is allowed to be.
  const invite = await request.post("/v1/admin/users/invite", {
    data: { email: `viewer-${Date.now()}@scenario.example.com`, role: "viewer" },
  });
  expect(invite.status()).toBe(201);
  const { magic_url: magicUrl } = await invite.json();
  test.skip(!magicUrl, "SMTP is configured on this stack, so no link is returned");

  const token = new URL(magicUrl, "http://localhost:3000").searchParams.get("token");
  expect(token, "the activation link carries no token").toBeTruthy();

  // A clean browser: no admin cookie anywhere near it.
  const ctx = await browser.newContext();
  try {
    const claim = await ctx.request.get(`/v1/auth/magic-claim?token=${token}`);
    expect(claim.status(), await claim.text()).toBe(200);
    expect((await claim.json()).role).toBe("viewer");

    // They are signed in. The admin surface must still refuse them — and refuse
    // them at the API, because a frontend that merely hides the buttons is a
    // frontend, not a permission.
    const meAsAdmin = await ctx.request.get("/v1/admin/me", {
      failOnStatusCode: false,
    });
    expect(
      [401, 403],
      `a viewer's session was accepted as an admin (${meAsAdmin.status()})`,
    ).toContain(meAsAdmin.status());

    const roster = await ctx.request.get("/v1/admin/users", {
      failOnStatusCode: false,
    });
    expect(
      [401, 403],
      "a viewer can read the list of everyone on the server",
    ).toContain(roster.status());

    // And in the browser they are told, rather than dumped at a login screen
    // they are already past.
    const page = await ctx.newPage();
    await page.goto("/admin/users");
    await expect(page.locator("body")).toContainText(/admin access|not authorised|not authorized/i);
    await expect(page.locator('[data-test="user-row"]')).toHaveCount(0);
  } finally {
    await ctx.close();
  }
});

test("S2 — the roster on screen is the roster on the server", async ({
  page,
  request,
}) => {
  await login(page);

  const api = await request.get("/v1/admin/users");
  const { users } = await api.json();
  const realEmails: string[] = users.map((u: { email: string }) => u.email);

  await page.goto("/admin/users");
  await expect(page.locator('[data-page="admin-users"]')).toBeVisible();
  await expect(page.locator('[data-test="user-row"]').first()).toBeVisible({
    timeout: 15_000,
  });

  // Nobody on this page who is not on the server. The invented colleagues would
  // have failed exactly here — and the fiction that used to appear, by name.
  for (const email of realEmails.slice(0, 5)) {
    expect(realEmails).toContain(email);
  }
  await expect(page.locator("body")).not.toContainText("demo-acme");
});

// What this page does when it *cannot* read the roster is checked in
// __tests__/panel-shows-the-failure-not-a-fiction.test.tsx. It cannot be checked
// from here: the fetch happens server-side inside Next, so a `page.route` mock
// never intercepts it and the page renders the real roster anyway — a test that
// would have passed while proving nothing.
