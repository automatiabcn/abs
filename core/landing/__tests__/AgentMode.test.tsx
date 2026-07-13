/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agent mode, from the client's side.
//
// The backend's guarantee is that a consequential tool call stops for a human.
// The client's job is not to undermine that: it must send agent mode only when
// the user turned it on, and it must show an approval-blocked call as blocked
// rather than quietly rendering it like any other result. A UI that implies an
// action happened when it is still waiting on a person is a worse lie than a
// crash.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const STREAM = readFileSync(
  join(__dirname, "..", "lib", "chat-stream.ts"),
  "utf8",
);
const CHAT_UI = readFileSync(
  join(__dirname, "..", "components", "chat", "index.tsx"),
  "utf8",
);
const CHAT_CLIENT = readFileSync(
  join(__dirname, "..", "app", "panel", "chat", "ChatClient.tsx"),
  "utf8",
);

describe("agent mode — the request", () => {
  it("asks for agent mode only when the user turned it on", () => {
    // `mode` is sent from the toggle's state, never hard-coded on: a request
    // that always said "agent" would put every plain question through a
    // multi-step loop and the provider bill that comes with it.
    expect(STREAM).toContain('mode: agentMode ? "agent" : "chat"');
    expect(STREAM).not.toContain('mode: "agent"');
  });

  it("defaults to plain chat", () => {
    expect(STREAM).toMatch(/agentMode\s*=\s*false/);
  });
});

describe("agent mode — the stream", () => {
  it("handles every event the loop emits", () => {
    // A frame the client drops is a step the user never sees. The loop's event
    // set is small and fixed; all of it is accounted for here.
    for (const event of [
      "agent-step",
      "approval-required",
      "agent-done",
      "agent-error",
    ]) {
      expect(STREAM, `unhandled event: ${event}`).toContain(`case "${event}":`);
    }
  });

  it("shows an approval-blocked call as waiting, not as done", () => {
    const branch = STREAM.split('case "approval-required":')[1]?.split("break;")[0] ?? "";
    expect(branch).toMatch(/approval/i);
    // It lands in toolCalls (so the user sees what was attempted) with a result
    // that says it has not run.
    expect(branch).toContain("toolCalls");
  });

  it("clears the step counter when the run ends, however it ends", () => {
    for (const ending of ['case "agent-done":', 'case "agent-error":']) {
      const branch = STREAM.split(ending)[1]?.split("break;")[0] ?? "";
      expect(branch, `${ending} leaves the step counter running`).toContain(
        "setAgentStep(null)",
      );
    }
  });
});

describe("agent mode — the control", () => {
  it("gives the toggle a pressed state and a step counter", () => {
    expect(CHAT_UI).toContain('data-test="agent-toggle"');
    expect(CHAT_UI).toContain("aria-pressed={agentMode}");
    // The live step label: an agent run is several provider calls long, and a
    // still spinner across that reads as a hang.
    expect(CHAT_UI).toMatch(/agentStep\s*\?\s*`Step \$\{agentStep\}`/);
  });

  it("cannot be flipped mid-run", () => {
    const toggle = CHAT_UI.split('data-test="agent-toggle"')[0].slice(-400);
    expect(toggle).toContain("disabled={isStreaming}");
  });

  it("remembers the user's choice across reloads", () => {
    expect(CHAT_CLIENT).toContain("AGENT_MODE_KEY");
    expect(CHAT_CLIENT).toContain("localStorage.setItem(AGENT_MODE_KEY");
  });
});
