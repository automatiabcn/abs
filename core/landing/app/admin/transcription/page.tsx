/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/transcription` canonical route. Was a 308 → /panel/transcription
// redirect that looped (Caddy sends /panel/* to the backend, which 308s
// /panel → /admin). Re-export the real client component so it renders on the
// landing directly. See app/admin/meetings/page.tsx for the full rationale.
"use client";

import TranscriptionPage from "@/app/panel/transcription/page";

export default function AdminTranscriptionPage() {
  return <TranscriptionPage />;
}
