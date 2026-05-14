/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2I UAT-038 — /panel/account/deletion-status — KVKK/GDPR
// 30-day grace window surface so the customer can see and cancel.
"use client";

import DeletionStatusBanner, {
  useDeletionStatus,
} from "@/components/DeletionStatusBanner";

export default function DeletionStatusPage() {
  const { data, error, refresh } = useDeletionStatus();

  async function onCancel() {
    await fetch("/v1/me/account/delete-cancel", { method: "POST" });
    await refresh();
  }

  return (
    <main className="mx-auto max-w-2xl p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Account deletion</h1>
      {error ? (
        <p className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      ) : null}
      {data ? (
        <DeletionStatusBanner data={data} onCancel={onCancel} />
      ) : (
        <p className="text-sm text-zinc-500">Loading…</p>
      )}
    </main>
  );
}
