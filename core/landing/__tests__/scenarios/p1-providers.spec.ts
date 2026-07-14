// the Providers page tells the truth about what is set up.
//
// This is the page an operator stares at when the product is not working, and
// the "test" button is the one thing they trust to tell them whether the problem
// is their key. Two ways it can betray them, and both have happened here before:
//
//   - reporting a provider "configured" when it is half-configured (Cloudflare
//     needs an account id as well as a token; a token-only save used to read as
//     ready while every single call failed);
//   - turning a provider that is merely *busy* into what looks like a broken
//     key, because the cascade threw a web exception the route never caught.
//
// So: a real key tests green, a broken key tests red, and neither is quiet
// about it.

import { expect, test } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("E1 — the status list only claims a provider is set up when it really is", async ({
  request,
}) => {
  const resp = await request.get("/v1/admin/providers/status");
  expect(resp.status(), await resp.text()).toBe(200);
  const { providers } = await resp.json();

  expect(Array.isArray(providers)).toBe(true);
  expect(providers.length).toBeGreaterThan(0);

  // Whatever the local stack has, at least one provider must be usable — the
  // free tier is the product's core promise, and a suite that passes against a
  // server with nothing configured is not testing the product.
  const configured = providers.filter((p: { configured: boolean }) => p.configured);
  expect(
    configured.length,
    "no provider is configured — the free tier cannot be working",
  ).toBeGreaterThan(0);

  // And keys never come back over the wire, not even truncated.
  const raw = await resp.text();
  expect(raw).not.toMatch(/gsk_|sk-|Bearer /);
});

// Same provider and the same cleanup as the failover scenario: a key written
// into a shared local stack and left there would quietly change what every other
// test is running against.
const BROKEN = "cerebras";
const DEAD_KEY = "csk-this-key-does-not-work-and-that-is-the-point";

test.afterEach(async ({ request }) => {
  await request.delete("/v1/admin/provider-keys", {
    data: { provider: BROKEN, owner_type: "org" },
  });
});

test("E1b — a broken key tests red, and says why", async ({ request }) => {
  // Point a provider at a key that cannot work, the way a customer does when
  // they paste the wrong thing, then press the button they press.
  const saved = await request.post("/v1/admin/provider-keys", {
    data: { provider: BROKEN, owner_type: "org", value: DEAD_KEY },
  });
  expect(saved.ok(), await saved.text()).toBe(true);

  const tested = await request.post(`/v1/admin/providers/${BROKEN}/test`, {
    failOnStatusCode: false,
  });

  // The button answers. It does not explode: a 5xx here is indistinguishable, to
  // the operator, from "your key is fine but the server is broken", which is the
  // one thing this button exists to rule out.
  expect(
    tested.status(),
    "the test button crashed instead of reporting a failure",
  ).toBe(200);

  const body = await tested.json();
  expect(body.ok, "a key that cannot work reported itself working").toBe(false);
  expect(String(body.error ?? ""), "the failure came back with no reason").not.toBe("");
});
