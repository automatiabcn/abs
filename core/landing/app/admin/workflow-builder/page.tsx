/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import { redirect } from "next/navigation";

// Consolidated: Workflow now lives in ONE place — the visual "Workflow Designer"
// (/admin/workflows) under Agentic Growth. This legacy natural-language builder
// used a separate node model and a duplicate "Workflow" nav entry, which was
// confusing. The route is kept as a redirect so old links don't 404; the
// natural-language synthesis backend (/v1/workflows/synthesize) stays available
// to be re-surfaced inside the Designer later.
export default function WorkflowBuilderRedirect() {
  redirect("/admin/workflows");
}
