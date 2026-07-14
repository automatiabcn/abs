// the usage page counts the traffic the customer actually generated.
//
// This is the page somebody opens when they are nervous about a bill, or when
// they want to know whether the free tier is really doing the work the product
// says it is. It is worth nothing if the numbers are stale, aspirational, or
// wired to a different source than the requests themselves.
//
// The test is small on purpose: read the counter, send one real message through
// the live cascade, read it again. The only claim being made is that a request
// the customer made shows up as a request the customer made — but that is the
// only claim the page exists to support, and no test made it.

import { expect, test } from "@playwright/test";

import { requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("M1 — a message sent in chat turns up in the usage figures", async ({
  page,
  request,
}) => {
  const before = await request.get("/v1/admin/usage");
  expect(before.status(), await before.text()).toBe(200);
  const callsBefore: number = (await before.json()).total_calls_24h ?? 0;

  // One real question, answered by a real provider — and a question nobody has
  // asked before, because the cascade caches. A fixed prompt makes this test pass
  // exactly once: on the second run the answer comes from cache, no provider is
  // called, and nothing is metered — which is correct behaviour (a cache hit must
  // not be billed twice) and a test that fails for a reason that has nothing to
  // do with what it is checking.
  const nonce = Date.now();
  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill(
    `In one word, what colour is a clear sky at noon? (question id ${nonce})`,
  );
  await input.press("Enter");
  const reply = await waitForStreamedReply(page);
  expect(reply.length).toBeGreaterThan(0);

  // The usage page has to have noticed. A counter that only moves for traffic
  // sent some other way is a counter that lies to the person paying the bill.
  await expect
    .poll(
      async () => {
        const after = await request.get("/v1/admin/usage");
        return (await after.json()).total_calls_24h ?? 0;
      },
      {
        timeout: 20_000,
        message: "a chat message never reached the usage figures",
      },
    )
    .toBeGreaterThan(callsBefore);
});

test("M1b — the free-path share is unknown, not 100%, on a server with no traffic", async ({
  request,
}) => {
  // Not a nitpick: "100% of your work ran on the free tier" is the product's
  // central claim, and a fresh install that has answered nothing must not
  // assert it. A fabricated number here is the most flattering possible lie and
  // the easiest one to believe.
  const usage = await request.get("/v1/admin/usage");
  expect(usage.status()).toBe(200);
  const body = await usage.json();

  const calls: number = body.total_calls_24h ?? 0;
  const pct = body.free_path?.pct_24h ?? null;

  if (calls === 0) {
    expect(pct, "an install with no traffic claimed a free-path percentage").toBeNull();
  } else {
    expect(pct).toBeGreaterThanOrEqual(0);
    expect(pct).toBeLessThanOrEqual(1);
  }
});
