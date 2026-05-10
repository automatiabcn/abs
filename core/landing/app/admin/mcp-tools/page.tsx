/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2B BUG-19/20/25/26 — `/admin/mcp-tools` canonical MCP tool
// browser. Pre-rc7 the sidebar /admin/mcp-tools entry redirected to
// /panel/tools (308); now it lands on a real page that re-exports the
// existing /panel/tools client component so the same TanStack Table +
// /v1/panel/tools fetch contract stays untouched.
"use client";

import ToolsPage from "@/app/panel/tools/page";

export default function AdminMcpToolsPage() {
  return <ToolsPage />;
}
