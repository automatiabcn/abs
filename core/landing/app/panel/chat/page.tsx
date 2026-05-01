// Q8 Phase A — `/panel/chat` premium chat UI. Wires the custom SSE hook
// (lib/chat-stream) to the 3-column layout and the session list.
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

export default function ChatPage() {
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
                  className="flex items-center justify-between rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
                >
                  <span>Hata: {error}</span>
                  <button
                    type="button"
                    onClick={retry}
                    className="text-xs underline hover:text-rose-100"
                  >
                    Tekrar dene
                  </button>
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
