// Sprint 21 / Faz C — chat client extracted into its own file so the
// /panel/chat route can next/dynamic-import it. Vercel AI SDK +
// react-markdown + the chat panel components only ship when the user
// actually navigates to /panel/chat — they no longer sit in the panel
// chrome bundle.
"use client";

import { useCallback, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";

import {
  ChatSidebar,
  EmptyState,
  MessageBubble,
  MessageInput,
  MetaSidebar,
} from "@/components/chat";
import {
  createSession,
  deleteSession,
  listSessions,
  loadHistory,
  useChat,
  type SessionListItem,
} from "@/lib/chat-stream";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatClient() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const sessionParam = params?.get("session");
  const initialSessionId = sessionParam ? Number(sessionParam) : undefined;

  const sessionsQuery = useQuery<SessionListItem[]>({
    queryKey: ["chat", "sessions"],
    queryFn: listSessions,
    refetchOnWindowFocus: true,
  });

  const {
    messages,
    setMessages,
    input,
    setInput,
    send,
    isStreaming,
    lastMeta,
    sessionId,
    abort,
    error,
    retry,
  } = useChat({
    initialSessionId,
    onSessionStarted: (id) => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      const url = new URL(window.location.href);
      url.searchParams.set("session", String(id));
      router.replace(`${url.pathname}?${url.searchParams.toString()}`);
    },
  });

  // Hydrate history when route param points to an existing session
  useEffect(() => {
    if (!initialSessionId) {
      setMessages([]);
      return;
    }
    let active = true;
    void loadHistory(initialSessionId).then((rows) => {
      if (!active) return;
      setMessages(rows);
    });
    return () => {
      active = false;
    };
  }, [initialSessionId, setMessages]);

  const newSession = useMutation({
    mutationFn: () => createSession(),
    onSuccess: (s) => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      router.push(`/panel/chat?session=${s.id}`);
    },
  });

  const removeSession = useMutation({
    mutationFn: deleteSession,
    onSuccess: (_, removedId) => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      if (sessionId === removedId) {
        router.push("/panel/chat");
      }
    },
  });

  const handlePickPrompt = useCallback(
    (prompt: string) => {
      setInput(prompt);
      void send(prompt);
    },
    [setInput, send],
  );

  const sessions = sessionsQuery.data ?? [];
  const activeId = sessionId ?? initialSessionId;
  const showEmpty = messages.length === 0 && !isStreaming;

  return (
    <div
      data-page="panel-chat"
      className="flex h-[calc(100vh-3.5rem)] min-h-0 w-full"
    >
      <ChatSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={(id) => router.push(`/panel/chat?session=${id}`)}
        onNew={() => newSession.mutate()}
        onDelete={(id) => removeSession.mutate(id)}
        isLoading={sessionsQuery.isLoading}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div>
            <h1 className="text-base font-semibold tracking-tight">
              Sohbet
            </h1>
            <p className="text-xs text-muted-foreground">
              Cascade router · 6 sağlayıcı · slash komut desteği
            </p>
          </div>
          {sessionsQuery.isFetching && (
            <Skeleton className="h-3 w-16" />
          )}
        </header>

        <section className="flex-1 overflow-y-auto px-6 py-6">
          {showEmpty ? (
            <EmptyState onPick={handlePickPrompt} />
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              className="mx-auto flex w-full max-w-3xl flex-col gap-4"
            >
              {messages.map((m, i) => (
                <MessageBubble key={i} msg={m} />
              ))}
              {error && (
                <div
                  role="alert"
                  data-test="chat-error-tile"
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
                >
                  <span>Hata: {error}</span>
                  <div className="flex items-center gap-2">
                    {/* Q10-L9-001 — cascade 503 routinely lands when the vault
                        has no provider key. Always offer the Configure path
                        next to the retry CTA so the user knows where to go. */}
                    <a
                      href="/admin/settings"
                      data-test="configure-cta"
                      className="rounded border border-rose-500/40 px-2 py-0.5 text-xs hover:bg-rose-500/20"
                    >
                      Sağlayıcı yapılandır
                    </a>
                    <button
                      type="button"
                      onClick={retry}
                      className="text-xs underline hover:text-rose-100"
                    >
                      Tekrar dene
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </section>

        <footer className="border-t border-border bg-card/30 p-4">
          <div className="mx-auto w-full max-w-3xl">
            <MessageInput
              value={input}
              onChange={setInput}
              onSubmit={() => send()}
              onAbort={abort}
              disabled={isStreaming}
              isStreaming={isStreaming}
            />
          </div>
        </footer>
      </main>
      <MetaSidebar meta={lastMeta} />
    </div>
  );
}
