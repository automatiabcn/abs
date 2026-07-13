// Sign in once, and let every scenario reuse the session.
//
// Not a speed optimisation. Logging in per test tripped the login rate limit
// (5/minute, a brute-force cap that is exactly right and should stay), and the
// suite started failing in whichever test happened to be sixth — a moving,
// meaningless failure that looks like flakiness and hides real ones. A person
// signs in once and then works; so does the suite.

import { test as setup } from "@playwright/test";

import { login, requireBackend } from "./helpers/stack";

export const ADMIN_STATE = "playwright/.auth/admin.json";

setup("sign in", async ({ page, request }) => {
  await requireBackend(request);
  await login(page);
  await page.context().storageState({ path: ADMIN_STATE });
});
