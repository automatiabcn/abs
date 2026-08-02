/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What a failed sign-in says to the person who just typed their password.
//
// Measured on the live site (2026-08-02): entering credentials produced the
// single line "HTTP 404". A status code is a fact about a protocol, not an
// answer to "what happened to me?" — the reader cannot tell whether they got
// the password wrong, whether their account is missing, or whether the site
// is broken, and each of those has a different next step.
//
// So the code is translated into the thing the reader would do next. Where
// the server sent its own explanation we prefer that, because it knows more
// than we do; the mapping below is for when it did not, or could not.

/** The server's own words, when it managed to send any. */
function serverDetail(payload: unknown): string {
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
  }
  return "";
}

export function signInMessage(status: number, payload?: unknown): string {
  const detail = serverDetail(payload);
  if (detail) {
    return detail;
  }
  if (status === 400 || status === 401 || status === 403) {
    return "That email and password did not match. Check both, or use a magic link.";
  }
  if (status === 404) {
    // On a self-hosted product a 404 here does not mean "no such user" — it
    // means the sign-in endpoint is not there, i.e. this page is not wired to
    // an ABS server. Saying "not found" would send the reader looking for
    // their account, which is the wrong place entirely.
    return "This page cannot reach an ABS server, so there is nothing to sign in to. If you are running ABS yourself, sign in at your own install instead.";
  }
  if (status === 429) {
    return "Too many attempts in a row. Wait a minute and try again.";
  }
  if (status === 502 || status === 503 || status === 504) {
    return "The ABS server is not answering right now. This is not your password — try again shortly.";
  }
  if (status >= 500) {
    return "The ABS server hit an error handling the sign-in. This is not your password.";
  }
  return `The server answered ${status} and sent no explanation, so this page cannot tell you why.`;
}

/** When the request never reached a server at all. */
export function networkMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const tail = raw.trim() ? ` (${raw.trim()})` : "";
  return `Could not reach the server to sign in — check your connection or the server address${tail}.`;
}
