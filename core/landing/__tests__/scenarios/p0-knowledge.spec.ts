// P0 — K1: a document goes in through the page a customer actually uses, and
// comes back out as a cited answer in chat.
//
// C3 already proves retrieval, but it seeds the index through the API. That
// leaves the whole first half of the journey untested: the upload form, the
// file input, the indexing that has to finish before the answer can exist. A
// customer does not have curl. They have a page with a button on it, and if
// that button drops the file on the floor, every downstream test still passes
// while the product is useless.
//
// The document is written here, at test time, with a fact in it that exists
// nowhere else on earth. A model that invents an answer gets it wrong, which is
// the only reason this test can tell knowing from guessing.

import { expect, test } from "@playwright/test";

import { requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

// Deliberately specific, and deliberately about nothing else in this suite. The
// first version of this document was about *onboarding*, which is what the
// meeting scenario asks its question about — so this document outranked the
// meeting in retrieval and broke a passing test. A scenario suite shares one
// index, and a document that answers someone else's question is a test that
// sabotages its neighbours.
const FACT = "The Kestrel account's annual pricing audit is always run in the last week of February.";
const DOC = [
  "# Kestrel account — pricing audit",
  "",
  FACT,
  "",
  "The audit is carried out by whoever signed the contract, and takes two days.",
].join("\n");

const FILENAME = `kestrel-pricing-audit-${Date.now()}.md`;

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test("K1 — a document uploaded on the Knowledge page becomes a cited answer in chat", async ({
  page,
}) => {
  await page.goto("/admin/rag");

  const fileInput = page.locator('[data-test="rag-file-input"]');
  await fileInput.waitFor({ state: "attached", timeout: 20_000 });

  // The real control, driven the way a person drives it: pick a file.
  await fileInput.setInputFiles({
    name: FILENAME,
    mimeType: "text/markdown",
    buffer: Buffer.from(DOC, "utf-8"),
  });

  // The upload has to visibly land. A page that swallows the file and says
  // nothing is the exact failure this scenario exists to catch, so we wait for
  // the document to appear in the list rather than for a spinner to stop.
  await expect(
    page.locator('[data-test="rag-doc-row"]').filter({ hasText: FILENAME.replace(/\.md$/, "") }),
  ).toBeVisible({ timeout: 60_000 });

  // Now ask about it in chat — the only proof that indexing actually happened,
  // as opposed to a row being drawn in a table.
  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill("/rag When is the Kestrel account's annual pricing audit run?");
  await input.press("Enter");

  const reply = await waitForStreamedReply(page);

  // February is in the document and nowhere else. Anything else is a guess.
  expect(reply).toMatch(/february/i);

  const citations = page.locator('[data-test="chat-citations"]').last();
  await expect(citations).toBeVisible();
  await expect(citations).toContainText("kestrel-pricing-audit");
});

// K4 — retrieval has to pick the *right* document, not merely a document.
//
// This is the scenario the suite was missing, and its absence hid a bug that
// broke document search completely: the embedding backend shipped as `mock`,
// whose vectors are sha256 of the text. Every existing knowledge test still
// passed. Chunks came back, citations rendered, an answer arrived — the chunks
// were simply unrelated to the question, and with a top-5 window the right one
// got swept in often enough to look fine.
//
// So this test puts two documents in that a bad ranker cannot tell apart, and
// asks a question only one of them answers. Retrieval that does not understand
// meaning cannot pass it by luck.
test("K4 — asking about one client does not answer from another client's file", async ({
  page,
}) => {
  const stamp = Date.now();
  const files = [
    {
      name: `harrier-support-hours-${stamp}.md`,
      body: "# Harrier account — support\n\nThe Harrier account's support window is 07:00 to 15:00 UTC, weekdays only.",
    },
    {
      name: `osprey-support-hours-${stamp}.md`,
      body: "# Osprey account — support\n\nThe Osprey account's support window is round the clock, including weekends.",
    },
  ];

  await page.goto("/admin/rag");
  const fileInput = page.locator('[data-test="rag-file-input"]');
  await fileInput.waitFor({ state: "attached", timeout: 20_000 });

  for (const f of files) {
    await fileInput.setInputFiles({
      name: f.name,
      mimeType: "text/markdown",
      buffer: Buffer.from(f.body, "utf-8"),
    });
    await expect(
      page.locator('[data-test="rag-doc-row"]').filter({ hasText: f.name.replace(/\.md$/, "") }),
    ).toBeVisible({ timeout: 60_000 });
  }

  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill("/rag Is the Osprey account's support cover available at the weekend?");
  await input.press("Enter");

  await waitForStreamedReply(page);

  // Assert on the answer, not on the whole message block: the block includes the
  // rendered sources, and Harrier's excerpt legitimately contains its own hours.
  const answer = (
    await page.locator('[data-test="chat-message"][data-role="assistant"]').last()
      .locator('[data-test="chat-message-text"]').innerText()
  ).toLowerCase();

  // Osprey's cover is round the clock; Harrier's is weekdays only. Answering
  // from the wrong client's file gives a confident, sourced, wrong answer — the
  // worst thing this product can do, and the one nobody catches by reading the
  // screen, because it looks exactly like the right one.
  expect(answer).toMatch(/round the clock|weekend/);
  expect(answer).not.toMatch(/weekdays only/);

  // And the source it leant on is Osprey's file, not Harrier's.
  const citations = page.locator('[data-test="chat-citations"]').last();
  await expect(citations).toBeVisible();
  await expect(citations.locator('[data-test="chat-citation"]').first()).toContainText(
    "osprey-support-hours",
  );
});
