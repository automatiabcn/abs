// P0 — C2: a provider dies and the answer still lands.
//
// This is the promise the product is sold on. Everything else in the panel is a
// feature; this is the reason to run your own server at all. So it gets proved
// the hard way — not with a mocked cascade in a unit test, but by putting a
// provider that will genuinely fail at the front of a real chain and then asking
// a real question through the real chat.
//
// The break is arranged through a path a customer actually has: a brought key
// goes to the front of the chain (that is what C7 proves), and a key that does
// not work fails when it is called, not when it is saved. So the first provider
// the cascade reaches is one that will refuse — exactly the mid-flight death the
// scenario describes — and the free providers behind it have to carry the answer
// without the person noticing anything worse than a pause.
//
// What makes this test honest is what it refuses to accept. An error message in
// the bubble is not an answer (`waitForStreamedReply` rejects those). "Nothing
// crashed" is not an answer either. The chip has to name a provider, and it has
// to name a *different* one than the broken key — because a cascade that quietly
// reports the dead provider as the answerer is a cascade that is lying.

import { expect, test } from "@playwright/test";

import { requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

// Cerebras is not configured on this server, so the only way it enters the chain
// is by someone bringing a key — and this key is not a real credential, so the
// call it fronts will fail.
const BROKEN = "cerebras";
const DEAD_KEY = "csk-this-key-does-not-work-and-that-is-the-point";

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test.afterEach(async ({ page }) => {
  await page.request.delete("/v1/admin/provider-keys", {
    data: { provider: BROKEN, owner_type: "org" },
  });
});

test("C2 — the first provider fails mid-question and the answer arrives anyway", async ({
  page,
}) => {
  // Put the broken provider at the head of the chain, the way a customer would:
  // by bringing a key for it.
  const saved = await page.request.post("/v1/admin/provider-keys", {
    data: { provider: BROKEN, owner_type: "org", value: DEAD_KEY },
  });
  expect(saved.ok(), await saved.text()).toBe(true);

  const chain = await (await page.request.get("/v1/cascade/providers")).json();
  expect(chain.active[0], "the broken provider must be the one tried first").toBe(BROKEN);
  expect(
    chain.active.length,
    "there has to be something behind it, or this proves nothing",
  ).toBeGreaterThan(1);

  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill("In two sentences: what is a reverse proxy?");
  await input.press("Enter");

  // A real answer, not an apology. waitForStreamedReply throws if the bubble
  // holds an error, which is the whole point: the customer must not find out
  // that a provider died.
  const reply = await waitForStreamedReply(page);
  expect(reply.length).toBeGreaterThan(40);

  // And the panel must be honest about who actually answered. If the chip says
  // the broken provider served this, the failover is bookkeeping, not truth.
  const chip = page.locator('[data-test="provider-chip"]').last();
  await expect(chip).toBeVisible();
  const who = (await chip.innerText()).trim().toLowerCase();
  expect(who).not.toBe("");
  expect(who, "the dead provider cannot be the one that answered").not.toContain(BROKEN);
});
