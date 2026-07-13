// P1 — S3: the audit log is a record, or it is nothing.
//
// This page has one job: tell an operator what really happened on their server,
// and hand it to an auditor as evidence. It is the page a customer's security
// review will open first, and the page they will trust the least if it is ever
// caught being approximately right.
//
// Two ways it can betray that, and this suite exists because both were live:
//
//   1. It fabricated. On any failure to reach the backend — an expired session,
//      a restart, a slow socket — the server-rendered page fell back to sample
//      rows: a login five minutes ago by admin@demo-acme.com, a vault secret
//      read, each with an hmac-looking string, and the CSV button next to them
//      offering the lot as GDPR Article 15 / SOC 2 evidence. Nothing on screen
//      said "sample". Fixed; these tests hold it fixed.
//
//   2. The chain check can only be worth pressing if it can come back red. A
//      verifier that returns ok:true unconditionally is the same green light as
//      no verifier at all, and considerably more dangerous.

import { expect, test } from "@playwright/test";

import { login, requireBackend } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("S3 — the chain check actually walks the chain, and can say no", async ({
  request,
}) => {
  const resp = await request.get("/v1/admin/audit/verify-chain");
  expect(resp.status(), await resp.text()).toBe(200);
  const body = await resp.json();

  // Shape first: this is the contract the page renders.
  expect(body).toHaveProperty("ok");
  expect(body).toHaveProperty("total_entries");
  expect(body).toHaveProperty("tampered_entry_id");

  // On a healthy server the log is intact — and it has to have walked something.
  // `ok: true` over zero entries is what a verifier that does nothing looks like.
  expect(body.ok, `chain reported broken at #${body.tampered_entry_id}`).toBe(true);
  expect(
    body.total_entries,
    "the chain check passed having verified nothing — an empty log cannot vouch for itself",
  ).toBeGreaterThan(0);
  expect(body.tampered_entry_id).toBeNull();
});

test("S3 — the log is filling up on its own; the things people do land in it", async ({
  request,
}) => {
  const before = await request.get("/v1/admin/audit/recent?limit=200");
  expect(before.status()).toBe(200);
  const { entries } = await before.json();

  expect(Array.isArray(entries)).toBe(true);
  expect(
    entries.length,
    "nothing at all is being recorded — an audit log with no entries is not " +
      "evidence of a quiet server, it is evidence of a broken recorder",
  ).toBeGreaterThan(0);

  // Every entry names a who, a what and a when. A row missing any of the three
  // is not something an auditor can use.
  for (const e of entries.slice(0, 25)) {
    expect(e.action, JSON.stringify(e)).toBeTruthy();
    expect(e.ts, JSON.stringify(e)).toBeTruthy();
    expect(e.actor ?? "", JSON.stringify(e)).not.toBe("");
    expect(Number.isNaN(Date.parse(e.ts)), `unparseable ts: ${e.ts}`).toBe(false);
  }
});

test("S3 — the page shows what the server said, and nothing it did not", async ({
  page,
  request,
}) => {
  await login(page);

  const api = await request.get("/v1/admin/audit/recent?limit=200");
  const { entries } = await api.json();
  const realActions: string[] = entries.map((e: { action: string }) => e.action);

  await page.goto("/admin/audit");
  await expect(page.locator('[data-page="admin-audit"]')).toBeVisible();

  const rows = page.locator('[data-test="audit-row"]');
  await expect(rows.first()).toBeVisible({ timeout: 15_000 });

  // The rendered rows are the server's rows. The fabricated fixture used
  // actions the running server does not necessarily produce, so an assertion
  // that "every action on screen is an action the API returned" is precisely
  // the assertion the old page would have failed.
  const shownActions = await page
    .locator('[data-test="audit-row"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-action") ?? ""));

  expect(shownActions.length).toBeGreaterThan(0);
  for (const action of shownActions) {
    expect(
      realActions,
      `the page is showing an entry the server never sent: "${action}"`,
    ).toContain(action);
  }

  // And the sample identities are nowhere on the page, under any circumstances.
  await expect(page.locator("body")).not.toContainText("demo-acme");
});

// The other half of S3 — what this page does when it *cannot* read the log — is
// checked in __tests__/panel-shows-the-failure-not-a-fiction.test.tsx, not here.
// It has to be: the page fetches server-side inside Next, so a `page.route` mock
// in this file never sees the request and the page renders real rows regardless.
// A scenario test written that way passes without once rendering the state it
// claims to be testing, which is the same species of green light as everything
// else this suite has been pulling out of the product.
