// P0 — the approval loop, and the race that must not double-send it.
//
// G1  An approval-gated agent proposes an action, it waits for a person, the
//     person approves it in the panel, and the action fires — once, with a
//     trail in the outbox.
// X3  Two approvals of the same item land at the same instant (a double-click,
//     a retried request, two operators). Exactly one action may fire. This is
//     the scenario with money in it: the item is an outbound message, and
//     sending it twice is a customer-visible mistake no unit test would catch,
//     because the bug only exists when two requests overlap.

import { expect, test, type APIResponse } from "@playwright/test";

import { requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

// The session comes from auth.setup.ts — signing in per test trips the login
// rate limit and turns a real suite into a flaky one.
test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

/** Run the high-risk drafting agent — it always stops for a person. */
async function proposeAction(page: import("@playwright/test").Page): Promise<number> {
  const res = await page.request.post("/v1/agents/outbound_draft/run", {
    data: { task: "Draft a short follow-up email to the Falcon account about the retainer." },
    timeout: 120_000,
  });
  expect(res.ok(), await res.text()).toBe(true);

  const body = await res.json();
  // The gate is the agent's, not the panel's: a high-risk agent must come back
  // asking, never having acted.
  expect(body.requires_approval, "a high-risk agent answered without asking").toBe(true);
  expect(body.approval?.id, "no approval item was opened").toBeTruthy();
  return body.approval.id as number;
}

async function outboxFor(
  page: import("@playwright/test").Page,
  approvalId: number,
): Promise<unknown[]> {
  const res = await page.request.get("/v1/approvals/outbox");
  expect(res.ok()).toBe(true);
  const body = await res.json();
  const rows: Array<{ approval_item_id?: number }> = body.actions ?? body.items ?? [];
  return rows.filter((r) => r.approval_item_id === approvalId);
}

test("G1 — a proposed action waits for a person, then fires when approved", async ({ page }) => {
  const approvalId = await proposeAction(page);

  // Nothing has happened yet. That is the product's central promise: the
  // assistant drafted, and the draft is sitting still.
  expect(await outboxFor(page, approvalId)).toHaveLength(0);

  await page.goto("/admin/approvals");
  await expect(
    page.locator(`[data-test="approval-item"][data-approval-id="${approvalId}"]`),
  ).toBeVisible({ timeout: 30_000 });

  const decision = await page.request.post(`/v1/approvals/${approvalId}/decide`, {
    data: { decision: "approve", note: "" },
  });
  expect(decision.ok(), await decision.text()).toBe(true);
  expect((await decision.json()).status).toBe("approved");

  // Approved means acted on, and the outbox is where an operator proves it.
  const fired = await outboxFor(page, approvalId);
  expect(fired).toHaveLength(1);
});

test("G1b — rejecting it means nothing happens, and it cannot be revived", async ({ page }) => {
  // The other half of the promise, and the half nobody tests. "Approved sends
  // it" is worth nothing unless "rejected does not" is equally certain — a
  // reject that quietly sends anyway is the single worst bug this product could
  // ship, because the operator believes they stopped it.
  const approvalId = await proposeAction(page);

  await page.goto("/admin/approvals");
  const item = page.locator(`[data-test="approval-item"][data-approval-id="${approvalId}"]`);
  await expect(item).toBeVisible({ timeout: 30_000 });

  // Rejected through the panel button, not the API: the button is what an
  // operator actually presses, and it is the button that has to be wired right.
  await item.getByRole("button", { name: /reject/i }).click();

  await expect(page.locator('[data-test="action-result"]')).toContainText(/rejected|nothing was done/i, {
    timeout: 30_000,
  });

  expect(await outboxFor(page, approvalId), "a rejected action was sent anyway").toHaveLength(0);

  // And approving it afterwards must not resurrect it. A decided item is
  // decided; a second decision that fires the action would make the reject a
  // suggestion rather than a refusal.
  const revive = await page.request.post(`/v1/approvals/${approvalId}/decide`, {
    data: { decision: "approve", note: "" },
  });
  expect([400, 409]).toContain(revive.status());
  expect(await outboxFor(page, approvalId), "a rejected action was revived").toHaveLength(0);
});

test("X3 — approving the same item twice at once still sends it once", async ({ page }) => {
  const approvalId = await proposeAction(page);

  // Fired together, not one after the other: a sequential second approval is
  // caught by the status check and proves nothing. The bug being tested lives
  // in the window where both requests still see "pending".
  const decide = () =>
    page.request.post(`/v1/approvals/${approvalId}/decide`, {
      data: { decision: "approve", note: "" },
    });
  const results: APIResponse[] = await Promise.all([decide(), decide()]);

  // Both callers may legitimately be told "approved" — the item *is* approved.
  // What must not happen twice is the send.
  for (const res of results) {
    expect([200, 400, 409]).toContain(res.status());
  }

  const fired = await outboxFor(page, approvalId);
  expect(fired, "the outbound message was sent more than once").toHaveLength(1);
});
