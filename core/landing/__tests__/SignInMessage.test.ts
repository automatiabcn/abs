/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 */

// What a failed sign-in tells the person who just typed their password.
//
// Measured on the live deployment (2026-08-02): entering credentials against
// a landing with no backend behind it produced one line — "HTTP 404". A
// status code is a fact about a protocol, not an answer to "what happened to
// me?", and each possible cause has a different next step: retype the
// password, wait, or go to your own install. The reader could not tell which.

import { describe, expect, it } from "vitest";

import { networkMessage, signInMessage } from "../app/login/signInMessage";

describe("sign-in failure messages", () => {
  it("never shows a bare status code", () => {
    for (const status of [400, 401, 403, 404, 418, 429, 500, 502, 503, 504]) {
      const msg = signInMessage(status);
      expect(msg).not.toMatch(/^HTTP \d+$/);
      expect(msg.length).toBeGreaterThan(20);
      expect(msg).toMatch(/[.!]$/);
    }
  });

  it("prefers what the server said over anything we could guess", () => {
    expect(signInMessage(401, { detail: "This account is locked." })).toBe(
      "This account is locked.",
    );
    // Empty or absent detail falls through to our own wording rather than
    // rendering a blank box.
    expect(signInMessage(401, { detail: "   " })).toMatch(/did not match/);
    expect(signInMessage(401, {})).toMatch(/did not match/);
    expect(signInMessage(401, null)).toMatch(/did not match/);
  });

  it("blames the password only when the password is what was rejected", () => {
    expect(signInMessage(401)).toMatch(/did not match/);
    expect(signInMessage(403)).toMatch(/did not match/);
    // A server that is down is not a wrong password, and saying so spares
    // somebody retyping a password that was right all along.
    expect(signInMessage(503)).toMatch(/not your password/);
    expect(signInMessage(500)).toMatch(/not your password/);
  });

  it("reads a 404 here as 'no server', not 'no account'", () => {
    // On a self-hosted product the sign-in endpoint 404s when the page is not
    // wired to a backend. Calling that "not found" would send the reader
    // hunting for their account, which is the wrong place entirely.
    const msg = signInMessage(404);
    expect(msg).toMatch(/cannot reach an ABS server/);
    expect(msg).toMatch(/your own install/);
    expect(msg).not.toMatch(/password/i);
  });

  it("says an unexplained status is unexplained rather than inventing a cause", () => {
    expect(signInMessage(418)).toMatch(/418/);
    expect(signInMessage(418)).toMatch(/no explanation/);
  });

  it("a request that never arrived says so, and keeps the detail", () => {
    const msg = networkMessage(new Error("Failed to fetch"));
    expect(msg).toMatch(/Could not reach the server/);
    expect(msg).toMatch(/Failed to fetch/);
    // A thrown non-Error must not render as "[object Object]".
    expect(networkMessage(undefined)).toMatch(/Could not reach the server/);
    expect(networkMessage(undefined)).not.toMatch(/undefined/);
  });
});
