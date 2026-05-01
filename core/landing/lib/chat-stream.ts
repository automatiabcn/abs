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
  | { type: "tool-call"; name: string; args: ToolCall["args"] }
  | { type: "tool-result"; name: string; result: string }
  | { type: "text"; content: string; provider: string }
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
}

export function useChat({
  initialSessionId,
  onSessionStarted,
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

      try {
        const res = await fetch("/v1/chat/completions", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            messages: [{ role: "user", content }],
            stream: true,
          }),
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
        abortRef.current = null;
      }
    },
    [input, isStreaming, sessionId, consumeStream, updateLastAssistant],
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
