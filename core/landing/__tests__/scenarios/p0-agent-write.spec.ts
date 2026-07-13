// P0 — the assistant asks to change something, and a person decides.
//
// A1  The assistant is asked to save a note. The file does not appear. An
//     approval does — carrying the exact call — and the assistant says so.
// A2  The operator approves it, and only then does the file land on disk.
//
// This is the claim the whole product rests on, so it is checked against a real
// server with writing switched ON: the guarantee is not "the write tool is
// careful", it is that the chat path structurally cannot execute a write, and
// the only code that can run one is the approval path.

import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

// The one folder the local server opened up (ABS_AGENT_FS_ROOTS). The scenario
// runs on the same machine as the server, so "did it write the file" is a
// question we can answer by looking.
const SANDBOX = path.resolve(
  __dirname,
  "../../../backend/.localrun/agent-sandbox",
);
const TARGET = path.join(SANDBOX, "scenario-note.md");

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
  mkdirSync(SANDBOX, { recursive: true });
  rmSync(TARGET, { force: true });
});

test("A1+A2 — a write waits for a person, then happens exactly once they say yes", async ({
  page,
}) => {
  const before = await page.request.get("/v1/approvals?status=pending");
  const pendingBefore: Array<{ id: number }> =
    (await before.json()).items ?? (await before.json()).approvals ?? [];
  const knownIds = new Set(pendingBefore.map((item) => item.id));

  await page.goto("/admin/chat");
  const toggle = page.locator('[data-test="agent-toggle"]');
  await toggle.waitFor({ timeout: 20_000 });
  if ((await toggle.getAttribute("aria-pressed")) !== "true") await toggle.click();

  const input = page.locator('[data-test="message-input"] textarea');
  await input.fill(
    `Save a file at ${TARGET} containing exactly: Falcon retainer confirmed.`,
  );
  await input.press("Enter");
  await waitForStreamedReply(page);

  // Nothing was written. The model wanted to; that is not the same thing.
  expect(existsSync(TARGET), "the assistant wrote a file without being approved").toBe(false);

  // What it produced instead is a decision waiting for a person.
  const after = await page.request.get("/v1/approvals?status=pending");
  const body = await after.json();
  const pending: Array<{ id: number; channel: string; proposed_message: string }> =
    body.items ?? body.approvals ?? [];
  const fresh = pending.filter((item) => !knownIds.has(item.id) && item.channel === "agent_tool");
  expect(fresh, "no approval was opened for the write").toHaveLength(1);

  // And the approval carries the call itself, not a paraphrase of it — the
  // operator approves what will actually run.
  const call = JSON.parse(fresh[0].proposed_message);
  expect(call.name).toBe("fs_write");
  expect(call.args.path).toBe(TARGET);

  // Now the person says yes.
  const decision = await page.request.post(`/v1/approvals/${fresh[0].id}/decide`, {
    data: { decision: "approve", note: "" },
  });
  expect(decision.ok(), await decision.text()).toBe(true);

  expect(existsSync(TARGET), "approving the write did not write the file").toBe(true);
});
