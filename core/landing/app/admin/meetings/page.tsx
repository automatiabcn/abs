/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/meetings` canonical route the sidebar advertises. Previously this
// 308-redirected to /panel/meetings, but Caddy routes /panel/* to the backend
// (legacy /panel → /admin deprecation), so /admin/meetings → /panel/meetings →
// /admin/meetings looped forever (ERR_TOO_MANY_REDIRECTS). Re-export the real
// client component here — same pattern as /admin/mcp-tools and /admin/quota —
// so the page renders on the landing without any /panel round-trip.
"use client";

import MeetingsPage from "@/app/panel/meetings/page";

export default function AdminMeetingsPage() {
  return <MeetingsPage />;
}
