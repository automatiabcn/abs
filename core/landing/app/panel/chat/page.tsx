// Sprint 21 / Faz C — thin route wrapper. The chat client (which
// pulls in lib/chat-stream + Vercel AI SDK + react-markdown +
// components/chat) is dynamically imported so the panel chrome route
// no longer carries the chat surface in its initial bundle.
"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

const ChatClient = dynamic(() => import("./ChatClient"), {
  ssr: false,
  loading: () => (
    <div
      data-page="panel-chat"
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
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div>
            <h1 className="text-base font-semibold tracking-tight">Sohbet</h1>
            <p className="text-xs text-muted-foreground">Yükleniyor…</p>
          </div>
        </header>
        <section className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </section>
      </main>
    </div>
  ),
});

export default function ChatPage() {
  return <ChatClient />;
}
