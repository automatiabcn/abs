/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Onboarding analytics receiver. Forwards events to LangFuse via the
// backend `/v1/internal/onboarding-event` proxy. Failure mode: 202 Accepted
// even on downstream timeout so the client never waits longer than 200 ms.
import { NextResponse, type NextRequest } from "next/server";

const BACKEND = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";
const FORWARD_PATH = "/v1/internal/onboarding-event";

export async function POST(req: NextRequest) {
  let body: unknown = null;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Fire-and-forget — we don't block the user on a downstream stall.
  void fetch(`${BACKEND}${FORWARD_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(800),
  }).catch(() => undefined);

  return NextResponse.json({ ok: true }, { status: 202 });
}
