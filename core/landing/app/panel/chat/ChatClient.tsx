/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Chat client extracted into its own file so the
// /panel/chat route can next/dynamic-import it. Vercel AI SDK +
// react-markdown + the chat panel components only ship when the user
// actually navigates to /panel/chat — they no longer sit in the panel
// chrome bundle.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
import { PromptLibrary } from "@/components/chat/PromptLibrary";
import type { PromptLang } from "@/lib/prompt-library";
import {
  createSession,
  deleteSession,
  listSessions,
  loadHistory,
  useChat,
  type SessionListItem,
} from "@/lib/chat-stream";
import { loadDraft, saveDraft } from "@/lib/chat-draft";
import { Skeleton } from "@/components/ui/skeleton";

const AGENT_MODE_KEY = "abs.chat.agent";

export default function ChatClient() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const sessionParam = params?.get("session");
  const initialSessionId = sessionParam ? Number(sessionParam) : undefined;

  // A chaos drill found this: under cascade 503 the default
  // retry: 3 with backoff keeps isLoading=true for ~15s and the user
  // sees only a spinner. Cap retries so the error path is reached
  // quickly and surfaced via the sessions-error-tile banner below.
  const sessionsQuery = useQuery<SessionListItem[]>({
    queryKey: ["chat", "sessions"],
    queryFn: listSessions,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  // Agent mode is a per-session choice the user makes, and it persists across
  // reloads: someone who works this way keeps working this way, and someone who
  // wants a plain quick answer is not opted into three provider calls by us.
  const [agentMode, setAgentMode] = useState(false);

  useEffect(() => {
    try {
      setAgentMode(localStorage.getItem(AGENT_MODE_KEY) === "1");
    } catch {
      /* localStorage unavailable — default off */
    }
  }, []);

  const toggleAgent = useCallback(() => {
    setAgentMode((on) => {
      const next = !on;
      try {
        localStorage.setItem(AGENT_MODE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

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
    agentStep,
  } = useChat({
    initialSessionId,
    agentMode,
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

  // IndexedDB-backed draft persistence. Restores
  // user input across reloads / offline blips. Only restores on
  // cold mount when input is empty (don't clobber a fast typer).
  const draftHydratedRef = useRef(false);
  useEffect(() => {
    if (draftHydratedRef.current) return;
    let active = true;
    void loadDraft().then((draft) => {
      draftHydratedRef.current = true;
      if (!active) return;
      if (draft && !input) {
        setInput(draft);
      }
    });
    return () => {
      active = false;
    };
    // Intentionally only depend on setInput identity — we want
    // a cold-mount-only restore.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setInput]);

  useEffect(() => {
    if (!draftHydratedRef.current) return;
    void saveDraft(input);
  }, [input]);

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

  // FAZ B (2026-05-08) — prompt-library drawer state. The drawer mounts
  // to the right of <main>; toggled from the chat sidebar footer + the
  // empty-state CTA. `lang` reads from localStorage on first paint and
  // defaults to "en" so the bundle is never blocked on hydration.
  const [showPromptLibrary, setShowPromptLibrary] = useState(false);
  const [lang, setLang] = useState<PromptLang>("en");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("abs_pref_lang");
    if (stored === "tr" || stored === "es" || stored === "en") {
      setLang(stored);
    }
  }, []);
  const handlePickFromLibrary = useCallback(
    (prompt: string) => {
      setInput(prompt);
      setShowPromptLibrary(false);
    },
    [setInput],
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
        onShowPrompts={() => setShowPromptLibrary((v) => !v)}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {sessionsQuery.isError && (
          <div
            role="alert"
            data-test="sessions-error-tile"
            className="flex flex-wrap items-center justify-between gap-3 border-b border-rose-500/30 bg-rose-500/10 px-6 py-2 text-sm text-rose-200"
          >
            <span>Could not load your conversations</span>
            <button
              type="button"
              onClick={() => sessionsQuery.refetch()}
              data-test="sessions-error-retry"
              className="rounded border border-rose-500/40 px-2 py-0.5 text-xs hover:bg-rose-500/20"
            >
              Tekrar dene
            </button>
          </div>
        )}
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div>
            <h1 className="text-base font-semibold tracking-tight">
              Sohbet
            </h1>
            <p className="text-xs text-muted-foreground">
              Answers come from whichever provider is up — type / for commands
            </p>
          </div>
          {sessionsQuery.isFetching && (
            <Skeleton className="h-3 w-16" />
          )}
        </header>

        <section className="flex-1 overflow-y-auto px-6 py-6">
          {showEmpty ? (
            <EmptyState
              onPick={handlePickPrompt}
              lang={lang}
              onShowAll={() => setShowPromptLibrary(true)}
            />
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
                    {/* Cascade 503 routinely lands when the vault
                        has no provider key. Always offer the Configure path
                        next to the retry CTA so the user knows where to go. */}
                    <a
                      href="/admin/settings"
                      data-test="configure-cta"
                      className="rounded border border-rose-500/40 px-2 py-0.5 text-xs hover:bg-rose-500/20"
                    >
                      Configure a provider
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
              agentMode={agentMode}
              onToggleAgent={toggleAgent}
              agentStep={agentStep}
            />
          </div>
        </footer>
      </main>
      <MetaSidebar meta={lastMeta} />
      {showPromptLibrary && (
        <PromptLibrary
          lang={lang}
          onPick={handlePickFromLibrary}
          onClose={() => setShowPromptLibrary(false)}
        />
      )}
    </div>
  );
}
