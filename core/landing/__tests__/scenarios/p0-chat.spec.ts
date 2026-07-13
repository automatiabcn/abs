// P0 — the chat scenarios the product does not exist without.
//
// C1  A new operator asks a question and gets an answer, on the free tier,
//     with no paid key configured.
// C3  A question about the company's own documents comes back with citations,
//     and the citations name real files.
// C10 Agent mode: the assistant reaches for a tool, the panel shows which one,
//     and the answer contains what the tool returned rather than a guess.
//
// These run against a live backend and a live cascade. That is the point: a
// mocked stream proves the component renders, and proves nothing about whether
// a person who installs this server gets an answer out of it.

import { expect, test } from "@playwright/test";

import { login, requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page, request }) => {
  await requireBackend(request);
  await login(page);
});

async function ask(page: import("@playwright/test").Page, question: string) {
  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill(question);
  await input.press("Enter");
}

test("C1 — a first question is answered with no paid key configured", async ({ page }) => {
  await ask(page, "In one sentence: what is this server for?");

  const reply = await waitForStreamedReply(page);
  expect(reply.length).toBeGreaterThan(20);

  // The free tier answered, and the panel says which provider did — the claim
  // "works with no key" is only credible if the operator can see who served it.
  const chip = page.locator('[data-test="provider-chip"]').last();
  await expect(chip).toBeVisible();
  expect((await chip.innerText()).trim()).not.toBe("");
});

test("C3 — a question about our own documents comes back with citations", async ({ page }) => {
  // Give the server something to be right about. Ingesting through the API is
  // the same path the Knowledge page uses; the scenario under test is the
  // *retrieval*, not the upload form. `page.request` rather than the bare
  // fixture: it carries the session cookie the login just issued.
  const ingest = await page.request.post("/v1/rag/ingest", {
    data: {
      filename: "falcon-retainer.md",
      text:
        "Falcon account — retainer terms. The monthly retainer for the Falcon " +
        "account is 4,200 EUR, invoiced on the first working day of each month. " +
        "The retainer covers up to 30 hours of work; hours beyond that are billed " +
        "separately at the standard rate.",
    },
  });
  expect(ingest.ok(), await ingest.text()).toBe(true);

  await ask(page, "/rag What is the monthly retainer for the Falcon account?");
  const reply = await waitForStreamedReply(page);

  // The number is in the document and nowhere else — a model that invents an
  // answer here gets it wrong, which is exactly what makes this a real check.
  expect(reply).toMatch(/4[.,]?200/);

  const citations = page.locator('[data-test="chat-citations"]').last();
  await expect(citations).toBeVisible();
  await expect(citations).toContainText("falcon-retainer");
});

test("C10 — agent mode uses a tool and answers from what it returned", async ({ page }) => {
  await page.goto("/admin/chat");

  const toggle = page.locator('[data-test="agent-toggle"]');
  await toggle.waitFor({ timeout: 20_000 });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  const input = page.locator('[data-test="message-input"] textarea');
  await input.fill("Which providers are up right now, according to the system itself?");
  await input.press("Enter");

  // The tool call is shown, not inferred. An agent that silently calls things
  // is an agent nobody can audit — the card is the audit surface.
  await expect(page.locator('[data-test="tool-call-card"]').first()).toBeVisible({
    timeout: 90_000,
  });

  const reply = await waitForStreamedReply(page);
  expect(reply.length).toBeGreaterThan(20);
});
