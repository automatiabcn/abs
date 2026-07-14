/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Two things found by using the panel as a customer, with a real provider key,
// rather than by reading it.
//
//  1. Every page in the panel said "Overview". /admin/dashboard maps to /panel
//     in REDIRECT_EQUIVALENTS, and the active check prefix-matched it, so /panel
//     was a prefix of /panel/chat, /panel/rag, /panel/system — everything. The
//     Overview domain is first in DOMAINS, so it won every time: the rail
//     highlight and the breadcrumb were wrong on every route but one.
//
//  2. Ask the agent for the server's status and it answered in a sentence, then
//     dumped forty lines of raw JSON into the conversation under it. The card is
//     a receipt now — what ran, and the evidence one click away.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToolCallCard } from "@/components/chat";
import { activeDomain, isActive } from "@/components/shell/domains";

describe("which page the panel thinks you are on", () => {
  it("chat is Assistant, not Overview", () => {
    expect(activeDomain("/panel/chat").id).toBe("assistant");
    expect(activeDomain("/admin/chat").id).toBe("assistant");
  });

  it("the panel root is still Overview", () => {
    expect(activeDomain("/panel").id).toBe("overview");
    expect(activeDomain("/admin/dashboard").id).toBe("overview");
  });

  it("Overview does not claim every panel route", () => {
    expect(isActive("/admin/dashboard", "/panel/chat")).toBe(false);
    expect(isActive("/admin/dashboard", "/panel/rag")).toBe(false);
    expect(isActive("/admin/dashboard", "/panel")).toBe(true);
  });

  it("the deeper equivalences still match their sub-routes", () => {
    expect(isActive("/admin/chat", "/panel/chat/42")).toBe(true);
  });
});

describe("what a tool call looks like in the conversation", () => {
  const call = {
    name: "system_status",
    args: {},
    result: JSON.stringify({ uptime_seconds: 167, overall: "ok" }, null, 2),
  };

  it("is collapsed: the payload is evidence, not the answer", () => {
    const { container } = render(<ToolCallCard call={call} />);
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("system_status")).toBeInTheDocument();
  });

  it("says how much it is hiding, so opening it is a choice", () => {
    render(<ToolCallCard call={call} />);
    expect(screen.getByText(/lines? · show/)).toBeInTheDocument();
  });
});
