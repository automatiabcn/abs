/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2B BUG-19/20/25/26 — `/admin/quota` canonical kota route. The
// PanelSidebar Operasyon group's "Kota" link now points here (was
// /panel/quota pre-rc7). Re-export the existing /panel/quota client
// component so the same /v1/system/quota_status contract + Tremor
// charts ship without duplication.
"use client";

import QuotaPage from "@/app/panel/quota/page";

export default function AdminQuotaPage() {
  return <QuotaPage />;
}
