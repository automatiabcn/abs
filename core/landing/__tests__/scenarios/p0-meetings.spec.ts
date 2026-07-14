// a recording becomes something you can ask about, and a broken one doesn't.
//
// T1  Upload a real meeting recording. It is transcribed, indexed, and a
//     question in chat comes back with the decision that was spoken aloud.
// T2  Upload two hours of silence. It transcribes into invented sentences —
//     that is what a dead microphone produces — and none of it may reach the
//     knowledge base. The panel says why instead of showing a green tick.
// T3  Upload the same recording twice. One meeting, one transcription, one copy
//     in the vector store.
//
// The speech fixture is real audio, not a mock: the point of the scenario is
// that the transcription path works, and a fake WAV proves nothing about it.

import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { requireBackend, waitForStreamedReply } from "./helpers/stack";

test.describe.configure({ mode: "serial" });

const SPOKEN = path.join(__dirname, "fixtures", "spoken-meeting.wav");

// The session comes from auth.setup.ts — signing in per test trips the login
// rate limit and turns a real suite into a flaky one.
test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

/**
 * A silent WAV, built here rather than committed.
 *
 * Long enough to trip the speech-density gate (which deliberately ignores short
 * clips — a ten-second voice note with one sentence in it is not a fault), and
 * far too big to be worth keeping in the repository as a binary.
 */
function silentWav(seconds: number): Buffer {
  const rate = 8_000;
  const samples = rate * seconds;
  const data = Buffer.alloc(samples * 2); // 16-bit mono, all zeroes: pure silence
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

async function upload(
  page: import("@playwright/test").Page,
  name: string,
  buffer: Buffer,
) {
  const res = await page.request.post("/v1/meetings/upload", {
    multipart: {
      audio: { name, mimeType: "audio/wav", buffer },
    },
    timeout: 180_000,
  });
  expect(res.ok(), await res.text()).toBe(true);
  return res.json();
}

test("T1 — a recorded decision becomes an answer in chat, with the meeting as its source", async ({
  page,
}) => {
  const meeting = await upload(page, "monday-standup.wav", readFileSync(SPOKEN));

  // It heard words, and it kept them.
  expect(meeting.status).toBe("done");
  expect(meeting.quality_note).toBe("");
  expect(meeting.indexed).toBe(true);
  const transcript = meeting.segments.map((s: { text: string }) => s.text).join(" ");
  expect(transcript.toLowerCase()).toContain("onboarding");

  // And now the thing that makes any of it worth doing: the meeting is
  // answerable. This decision was only ever spoken aloud — it is in no
  // document — so a model that invents an answer here gets it wrong.
  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill("When do we ship the new onboarding flow, according to our meeting?");
  await input.press("Enter");

  const reply = await waitForStreamedReply(page);
  expect(reply.toLowerCase()).toContain("friday");

  const citations = page.locator('[data-test="chat-citations"]').last();
  await expect(citations).toBeVisible();
});

test("T2 — a silent recording is kept, shown as such, and never indexed", async ({ page }) => {
  // Five minutes, not the two hours of the original incident: the gate keys on
  // speech per minute, so five minutes of nothing fails it exactly as two hours
  // of nothing does — and it does not ship 115 MB of zeroes to prove it.
  const meeting = await upload(page, "dead-mic.wav", silentWav(300));

  // Whatever the model heard in the room tone, it is not going into the
  // knowledge base to be cited back at someone months from now.
  expect(meeting.indexed).toBe(false);
  expect(meeting.quality_note).toBeTruthy();

  await page.goto("/admin/meetings");
  const badge = page.locator('[data-test="meeting-not-indexed"]').first();
  await expect(badge).toBeVisible({ timeout: 30_000 });
});

test("T4 — a deleted recording stops answering questions", async ({ page }) => {
  // The thing that could not be done at all: a recording of a private
  // conversation went in, was indexed, and answered questions from then on. The
  // panel let you read it and nothing else. So this checks the claim the Delete
  // button makes — not that the row disappeared, but that the assistant has
  // forgotten what was said in the room.
  const meeting = await upload(page, "confidential-call.wav", readFileSync(SPOKEN));
  expect(meeting.indexed).toBe(true);

  const gone = await page.request.delete(`/v1/meetings/${meeting.id}`);
  expect(gone.ok(), await gone.text()).toBe(true);

  // Not hidden. Gone.
  const fetched = await page.request.get(`/v1/meetings/${meeting.id}`, {
    failOnStatusCode: false,
  });
  expect(fetched.status()).toBe(404);

  // And the knowledge base has let go of it. This decision was spoken aloud and
  // written down nowhere else, so an answer that still names Friday is an answer
  // coming out of a recording the operator deleted.
  await page.goto("/admin/chat");
  const input = page.locator('[data-test="message-input"] textarea');
  await input.waitFor({ timeout: 20_000 });
  await input.fill("When do we ship the new onboarding flow, according to our meeting?");
  await input.press("Enter");

  const reply = await waitForStreamedReply(page);
  expect(
    reply.toLowerCase(),
    "a deleted recording was still answering questions in chat",
  ).not.toContain("friday");
});

test("T3 — the same recording uploaded twice is one meeting", async ({ page }) => {
  const audio = readFileSync(SPOKEN);
  const first = await upload(page, "standup.wav", audio);
  // Same bytes, different name — a re-sync, a retried upload, one recording on
  // two calendar events.
  const again = await upload(page, "standup-copy.wav", audio);

  expect(again.duplicate_of).toBe(first.id);
  expect(again.id).toBe(first.id);
});
