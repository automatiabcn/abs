/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// How a customer who owns this server gets back into it.
//
// The site had no sign-in link anywhere in its chrome: four marketing links and
// a "Manage" button that opens the Stripe billing portal. So the only way in was
// to guess the URL — and the obvious guesses are not pages. /admin/login and
// /panel/login fell through to the auth middleware, which sent them to
// /login?next=/admin/login: signing in *successfully* then landed them on a
// route that does not exist. The setup wizard's finish button pointed at the
// same dead address.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

function read(relative: string): string {
  return readFileSync(resolve(__dirname, "..", relative), "utf8");
}

describe("the way in", () => {
  it("the header carries a sign-in link", () => {
    const header = read("components/Header.tsx");
    expect(header).toMatch(/href="\/login"/);
    expect(header).toMatch(/Sign in/);
  });

  it("the guesses a customer types land on the login page", () => {
    const config = read("next.config.ts");
    for (const guess of ["/admin/login", "/panel/login", "/signin", "/sign-in"]) {
      expect(config).toContain(`source: "${guess}"`);
    }
  });

  it("signup offers a way back to sign-in", () => {
    const signup = read("app/signup/page.tsx");
    expect(signup).toMatch(/href="\/login"/);
  });

  it("the setup wizard finishes on a page that exists", () => {
    const wizard = read("../backend/app/static/setup/assets/setup.js");
    expect(wizard).toContain("/login?next=/panel/chat");
    expect(wizard).not.toContain("/admin/login");
    expect(wizard).not.toContain("/panel/login");
  });
});
