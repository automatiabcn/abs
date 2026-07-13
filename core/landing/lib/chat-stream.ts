/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase A — custom SSE parser for `/v1/chat/completions` and helpers
// for `/v1/chat/sessions[/{id}/messages]`. Keeps a tight grip on the
// custom event protocol (session/tool-call/tool-result/text/meta/[DONE]).
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ChatRole = "user" | "assistant" | "system" | "tool";

export interface ToolCall {
  name: string;
  args: { query?: string; [k: string]: unknown };
  result?: string;
}

export interface Citation {
  chunk_id: string;
  source: string;
  relevance_score?: number | null;
  excerpt?: string;
  page?: number | null;
}

export interface ChatMessage {
  id?: string | number;
  role: ChatRole;
  content: string;
  provider?: string;
  toolCalls?: ToolCall[];
  tokensUsed?: number;
  latencyMs?: number;
  mock?: boolean;
  createdAt?: string;
  citations?: Citation[];
}

export interface MetaEvent {
  provider: string;
  fallbackChain: string[];
  tokensUsed: number;
  latencyMs: number;
  mock: boolean;
}

export interface SessionListItem {
  id: number;
  title: string;
  tenant_slug: string;
  user_email: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export type SessionEvent =
  | { type: "session"; session_id: number; title: string }
  | { type: "tool-call"; name: string; args: ToolCall["args"]; level?: string }
  | { type: "tool-result"; name: string; result: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "text"; content: string; provider: string }
  // Agent mode. The assistant looks things up before it answers, and shows its
  // work as it goes — a silent spinner through three tool calls reads as a hang.
  | { type: "mode"; id: "agent" }
  | { type: "agent-step"; step: number }
  | { type: "approval-required"; name: string; args: ToolCall["args"] }
  | { type: "agent-done"; answer: string; degraded?: boolean }
  | { type: "agent-error"; reason: string; detail?: string }
  | {
      type: "meta";
      provider: string;
      fallback_chain: string[];
      tokens_used: number;
      latency_ms: number;
      mock: boolean;
    };

interface UseChatOptions {
  initialSessionId?: number;
  onSessionStarted?: (id: number) => void;
  /** Let the assistant call tools before answering. Off = plain one-shot chat. */
  agentMode?: boolean;
}

interface UseChatReturn {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  input: string;
  setInput: (v: string) => void;
  send: (override?: string) => Promise<void>;
  isStreaming: boolean;
  lastMeta: MetaEvent | null;
  sessionId: number | undefined;
  error: string | null;
  retry: () => void;
  abort: () => void;
  /** Which agent step is running, while one is. Null in plain chat. */
  agentStep: number | null;
}

export function useChat({
  initialSessionId,
  onSessionStarted,
  agentMode = false,
}: UseChatOptions = {}): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastMeta, setLastMeta] = useState<MetaEvent | null>(null);
  const [sessionId, setSessionId] = useState<number | undefined>(
    initialSessionId,
  );
  const [error, setError] = useState<string | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState<string | null>(null);
  const [agentStep, setAgentStep] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // Keep sessionId in sync if the caller switches sessions
  useEffect(() => {
    setSessionId(initialSessionId);
  }, [initialSessionId]);

  const updateLastAssistant = useCallback(
    (patch: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const idx = prev.length - 1;
        if (prev[idx].role !== "assistant") return prev;
        const next = prev.slice();
        next[idx] = patch(next[idx]);
        return next;
      });
    },
    [],
  );

  const consumeStream = useCallback(
    async (reader: ReadableStreamDefaultReader<Uint8Array>) => {
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nlIdx: number;
        while ((nlIdx = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, nlIdx);
          buffer = buffer.slice(nlIdx + 2);
          for (const rawLine of chunk.split("\n")) {
            if (!rawLine.startsWith("data:")) continue;
            const payload = rawLine.slice(5).trim();
            if (payload === "[DONE]") return;
            if (!payload) continue;
            let evt: SessionEvent;
            try {
              evt = JSON.parse(payload) as SessionEvent;
            } catch {
              continue;
            }
            switch (evt.type) {
              case "session":
                setSessionId(evt.session_id);
                onSessionStarted?.(evt.session_id);
                break;
              case "tool-call":
                updateLastAssistant((m) => ({
                  ...m,
                  toolCalls: [
                    ...(m.toolCalls ?? []),
                    { name: evt.name, args: evt.args },
                  ],
                }));
                break;
              case "citations":
                updateLastAssistant((m) => ({
                  ...m,
                  citations: evt.citations,
                }));
                break;
              case "tool-result":
                updateLastAssistant((m) => ({
                  ...m,
                  toolCalls: (m.toolCalls ?? []).map((tc) =>
                    tc.name === "rag" || tc.name === evt.name
                      ? { ...tc, result: evt.result }
                      : tc,
                  ),
                }));
                break;
              case "text":
                updateLastAssistant((m) => ({
                  ...m,
                  content: m.content + evt.content,
                  provider: evt.provider,
                }));
                break;
              case "meta": {
                const meta: MetaEvent = {
                  provider: evt.provider,
                  fallbackChain: evt.fallback_chain,
                  tokensUsed: evt.tokens_used,
                  latencyMs: evt.latency_ms,
                  mock: evt.mock,
                };
                setLastMeta(meta);
                updateLastAssistant((m) => ({
                  ...m,
                  provider: evt.provider,
                  tokensUsed: evt.tokens_used,
                  latencyMs: evt.latency_ms,
                  mock: evt.mock,
                }));
                break;
              }
              // --- agent mode ---
              case "agent-step":
                setAgentStep(evt.step);
                break;
              case "approval-required":
                // Shown as a tool call that stopped short: the assistant wanted
                // to do something consequential and is waiting on a person. The
                // decision itself is made in Approvals, not here.
                updateLastAssistant((m) => ({
                  ...m,
                  toolCalls: [
                    ...(m.toolCalls ?? []),
                    {
                      name: evt.name,
                      args: evt.args,
                      result: "Waiting for your approval — see Approvals.",
                    },
                  ],
                }));
                break;
              case "agent-done":
                setAgentStep(null);
                break;
              case "agent-error":
                setAgentStep(null);
                setError(
                  evt.reason === "all_providers_failed"
                    ? "Sağlayıcılara ulaşılamadı; lütfen tekrar deneyin."
                    : "Agent modu şu an kullanılamıyor.",
                );
                break;
            }
          }
        }
      }
    },
    [onSessionStarted, updateLastAssistant],
  );

  const send = useCallback(
    async (override?: string) => {
      const content = (override ?? input).trim();
      if (!content || isStreaming) return;

      setError(null);
      setLastUserMessage(content);
      setInput("");
      setIsStreaming(true);

      // Optimistic append: user message + empty assistant placeholder
      setMessages((prev) => [
        ...prev,
        { role: "user", content },
        { role: "assistant", content: "", provider: "" },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      // Q12-L20-001 — chat completions is a POST + SSE; the backend never
      // legitimately returns a 3xx, so `redirect: "error"` makes a
      // misconfigured proxy (e.g. Caddy redir loop) surface as a fetch
      // rejection rather than silently following until the browser's
      // hard 20-redirect ceiling. Combined with the existing AbortController
      // for user-initiated cancel, this keeps the UI honest under failure.
      try {
        const res = await fetch("/v1/chat/completions", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            messages: [{ role: "user", content }],
            stream: true,
            mode: agentMode ? "agent" : "chat",
          }),
          redirect: "error",
          signal: controller.signal,
        });
        if (!res.ok) {
          // Q10-L9-002 — surface the backend detail (e.g. "no_providers_configured")
          // instead of a bare HTTP status so the user knows whether to
          // configure a provider or retry. Falls back to status when the
          // body isn't JSON (FastAPI HTTPException is JSON by default).
          let detail: string | null = null;
          try {
            const body = await res.clone().json();
            if (typeof body?.detail === "string") detail = body.detail;
          } catch {
            try {
              detail = (await res.text()).slice(0, 200) || null;
            } catch {
              detail = null;
            }
          }
          if (detail && /no_providers_configured/i.test(detail)) {
            throw new Error(
              "Henüz sağlayıcı yapılandırılmadı. Sağlayıcı yapılandır bağlantısını kullanın.",
            );
          }
          throw new Error(detail ? `${res.status} · ${detail}` : `Backend ${res.status}`);
        }
        const reader = res.body?.getReader();
        if (!reader) throw new Error("Yanıt akışı boş");
        await consumeStream(reader);
      } catch (exc: unknown) {
        if ((exc as Error)?.name === "AbortError") {
          // user-initiated cancel — leave partial assistant content as-is
        } else {
          const msg =
            exc instanceof Error ? exc.message : "Bilinmeyen hata";
          setError(msg);
          updateLastAssistant((m) => ({
            ...m,
            content: m.content || `Hata: ${msg}`,
            provider: "none",
          }));
        }
      } finally {
        setIsStreaming(false);
        setAgentStep(null);
        abortRef.current = null;
      }
    },
    [input, isStreaming, sessionId, agentMode, consumeStream, updateLastAssistant],
  );

  const retry = useCallback(() => {
    if (!lastUserMessage) return;
    // Drop the last assistant placeholder if it errored
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.role === "assistant" && (!last.content || last.provider === "none")) {
        return prev.slice(0, -1);
      }
      return prev;
    });
    void send(lastUserMessage);
  }, [lastUserMessage, send]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    setMessages,
    input,
    setInput,
    send,
    isStreaming,
    lastMeta,
    sessionId,
    error,
    retry,
    abort,
    agentStep,
  };
}

export async function listSessions(): Promise<SessionListItem[]> {
  const res = await fetch("/v1/chat/sessions", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function loadHistory(
  sessionId: number,
): Promise<ChatMessage[]> {
  const res = await fetch(`/v1/chat/sessions/${sessionId}/messages`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const rows: Array<{
    id: number;
    role: ChatRole;
    content: string;
    provider: string | null;
    tool_calls: ToolCall[] | null;
    citations: Citation[] | null;
    tokens_used: number | null;
    latency_ms: number | null;
    created_at: string;
  }> = await res.json();
  return rows.map((r) => ({
    id: r.id,
    role: r.role,
    content: r.content,
    provider: r.provider ?? undefined,
    toolCalls: r.tool_calls ?? undefined,
    // Without this the sources vanish on reload: the answer streams with its
    // citations, the page rehydrates from the database, and the "[1]" markers
    // in the text end up pointing at nothing.
    citations: r.citations?.length ? r.citations : undefined,
    tokensUsed: r.tokens_used ?? undefined,
    latencyMs: r.latency_ms ?? undefined,
    createdAt: r.created_at,
  }));
}

export async function createSession(title?: string): Promise<SessionListItem> {
  const res = await fetch("/v1/chat/sessions", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId: number): Promise<void> {
  const res = await fetch(`/v1/chat/sessions/${sessionId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
}

export async function renameSession(
  sessionId: number,
  title: string,
): Promise<SessionListItem> {
  const res = await fetch(`/v1/chat/sessions/${sessionId}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
