// Shared setup for the scenario suite.
//
// These specs are the only ones in the repo that talk to a *real* backend with
// a real cascade behind it. Everything else mocks the network, which is right
// for a component test and useless for the question these specs exist to
// answer: does a person who installs this server get an answer out of it.
//
// So: no route mocking, no fixture responses, and no `test.skip()` when the
// backend is missing. A suite that skips itself when the thing it tests is
// absent reports green for a system that never ran — the failure mode this
// project has been bitten by before. If the stack is not up, the suite fails
// and says exactly how to bring it up.

import { expect, type APIRequestContext, type Page } from "@playwright/test";

// `admin@local` is the backend's bootstrap identity, but the wizard will not
// take it as the admin's address (no dot after the @, which is a real address
// rule and stays). The suite installs through the wizard, so it uses an address
// the wizard accepts — the same one a person would.
export const ADMIN_EMAIL = process.env.ABS_ADMIN_EMAIL ?? "admin@abs.local";
export const ADMIN_PASSWORD = process.env.ABS_ADMIN_PASSWORD ?? "CHANGEME";

const HOW_TO_START = [
  "The scenario suite needs a live backend on :8000.",
  "",
  "  export GROQ_API_KEY=...",
  "  cd core/backend && ./scripts/run_e2e_backend.sh",
  "",
  "It is deliberate that this fails instead of skipping: a suite that skips",
  "when the system is absent reports green for a system that never ran.",
].join("\n");

/** Fail loudly, and usefully, if the backend this suite exists to exercise isn't there. */
export async function requireBackend(request: APIRequestContext): Promise<void> {
  let ok = false;
  try {
    const res = await request.get("/healthz", { timeout: 5_000 });
    ok = res.ok();
  } catch {
    ok = false;
  }
  expect(ok, HOW_TO_START).toBe(true);
}

/** Sign in through the real login form — the same door a customer uses. */
export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator('form[data-hydrated="true"]').waitFor();
  await page.locator('input[type="email"]').fill(ADMIN_EMAIL);
  await page.locator('input[type="password"]').fill(ADMIN_PASSWORD);
  await page.getByTestId("login-submit").click();
  // Generous, and it has to be: against a dev server that has just started, the
  // click is the first thing that ever asks for the panel route, and Next
  // compiles it on demand. Twenty seconds was enough on a warm server and not on
  // a cold one, so the suite failed at the login form depending on what had been
  // compiled before it — which reads as the product being broken and is not.
  await page.waitForURL(/\/(admin|panel)/, { timeout: 90_000 });
  // Login lands somewhere and then the app redirects again. Navigating before
  // that second hop lands cancels it ("interrupted by another navigation"), so
  // wait for the dust to settle rather than for the first URL that matches.
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
}

/**
 * Wait for a streamed assistant reply to finish.
 *
 * The chat streams token by token, so "the text is there" is true long before
 * the answer is complete. Settling on a stable length is what a person waiting
 * for the reply actually does.
 */
export async function waitForStreamedReply(page: Page, timeoutMs = 90_000): Promise<string> {
  const assistant = page.locator('[data-test="chat-message"][data-role="assistant"]').last();
  await assistant.waitFor({ timeout: timeoutMs });

  // The bubble exists before the answer does — it renders "Thinking…" while the
  // model is still working. That placeholder is perfectly stable, so the loop
  // below used to settle on it and hand back a nine-character "reply": the chat,
  // knowledge and meetings scenarios were all asserting against the word
  // "Thinking…" and failing for a reason that had nothing to do with the product.
  await assistant.and(page.locator('[data-pending="false"]')).waitFor({ timeout: timeoutMs });

  let previous = "";
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await page.waitForTimeout(1_200);
    const current = (await assistant.innerText()).trim();
    if (current.length > 0 && current === previous) {
      assertNotAnError(current);
      return current;
    }
    previous = current;
  }
  throw new Error("the assistant never stopped streaming");
}

/**
 * The chat renders a failure as an assistant message like any other.
 *
 * This is the trap the first version of this suite fell into: "an answer came
 * back and it was longer than twenty characters" is true of
 * `Hata: 403 · license_not_activated`, so the scenario went green while chat
 * was completely broken. Every reply is checked here — a test that can pass on
 * an error message is worse than no test, because it is believed.
 */
function assertNotAnError(reply: string): void {
  const looksLikeFailure =
    /^(hata|error)\s*[:·]/i.test(reply) ||
    /\b(license_not_activated|license_revoked|no_provider_available|provider_error)\b/i.test(reply);
  expect(looksLikeFailure, `the assistant replied with an error: ${reply}`).toBe(false);
}
