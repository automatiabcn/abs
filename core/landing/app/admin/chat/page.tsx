/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/chat` is now the canonical chat
// route the sidebar advertises (was a 308 redirect to /panel/chat
// pre-rc7). This wrapper imports the same dynamic ChatClient the
// /panel/chat page uses so the surface stays bundle-equivalent — just
// the URL changes.
"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

const ChatClient = dynamic(() => import("@/app/panel/chat/ChatClient"), {
  ssr: false,
  loading: () => (
    <div
      data-page="admin-chat"
      className="flex h-[calc(100vh-3.5rem)] min-h-0 w-full"
    >
      <aside className="hidden w-64 flex-col border-r border-border bg-card/30 p-3 md:flex">
        <Skeleton className="h-8 w-full" />
        <div className="mt-3 space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </aside>
      <section className="flex flex-1 flex-col p-6">
        <Skeleton className="mb-3 h-7 w-72" />
        <Skeleton className="mb-2 h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </section>
    </div>
  ),
});

export default function AdminChatPage() {
  return <ChatClient />;
}
