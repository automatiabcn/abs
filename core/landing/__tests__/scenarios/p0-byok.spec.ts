// bringing your own key changes who answers you.
//
// The free tier is the default and is meant to be good enough that most people
// never look past it. But someone who pastes in their own paid key has said
// something, and the server has to hear it: their key answers, and the
// operator's free providers stand behind it as the fallback.
//
// The failure this guards against is silent. The key saves, the panel shows a
// green row, and every question still goes to the free tier — because the chain
// sorted free-first and the paid key sat last. Nothing errors. You have simply
// bought nothing.
//
// The key here is deliberately not a real one: what is under test is the
// routing decision, not a paid call. A live call on someone's own credentials is
// not something a test suite should be making.

import { expect, test } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

const BROUGHT = "cerebras"; // not configured on this server: it can only be here via BYOK
const FAKE_KEY = "csk-scenario-key-not-a-real-credential";

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

async function chain(page: import("@playwright/test").Page) {
  const res = await page.request.get("/v1/cascade/providers");
  expect(res.ok(), await res.text()).toBe(true);
  return res.json();
}

test.afterEach(async ({ page }) => {
  await page.request.delete("/v1/admin/provider-keys", {
    data: { provider: BROUGHT, owner_type: "org" },
  });
});

test("C7 — a key you bring answers you, and the free chain still stands behind it", async ({
  page,
}) => {
  const before = await chain(page);
  expect(before.active[0], "the free tier should lead when nobody brought a key").toBe("groq");
  expect(before.active).not.toContain(BROUGHT);

  const saved = await page.request.post("/v1/admin/provider-keys", {
    data: { provider: BROUGHT, owner_type: "org", value: FAKE_KEY },
  });
  expect(saved.ok(), await saved.text()).toBe(true);

  const after = await chain(page);

  // The provider the server never heard of is now in the chain — and at the
  // front of it, because someone chose it.
  expect(after.active[0], "the brought key was not put first").toBe(BROUGHT);
  expect(after.byok).toContain(BROUGHT);

  // The free providers are still there, behind it. Bringing a key buys you a
  // preference, not a single point of failure.
  expect(after.active).toContain("groq");
  expect(after.active.indexOf("groq")).toBeGreaterThan(0);

  // And it is no longer listed as something the server is missing — it isn't.
  expect(after.missing).not.toContain(BROUGHT);
});

test("C7b — taking the key away puts you back on the free tier, cleanly", async ({ page }) => {
  await page.request.post("/v1/admin/provider-keys", {
    data: { provider: BROUGHT, owner_type: "org", value: FAKE_KEY },
  });
  expect((await chain(page)).active[0]).toBe(BROUGHT);

  const removed = await page.request.delete("/v1/admin/provider-keys", {
    data: { provider: BROUGHT, owner_type: "org" },
  });
  expect(removed.ok(), await removed.text()).toBe(true);

  const after = await chain(page);
  expect(after.active[0]).toBe("groq");
  expect(after.active).not.toContain(BROUGHT);
  expect(after.byok).not.toContain(BROUGHT);
});
