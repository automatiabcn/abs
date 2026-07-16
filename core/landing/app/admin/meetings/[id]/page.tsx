/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/meetings/{id}` canonical detail route. Re-exports the real client
// component so "Open" on the meetings list resolves on the landing without a
// /panel round-trip (Caddy routes /panel/* to the backend — see
// app/admin/meetings/page.tsx for the redirect-loop history).
"use client";

import MeetingDetailPage from "@/app/panel/meetings/[id]/page";

export default function AdminMeetingDetailPage() {
  return <MeetingDetailPage />;
}
