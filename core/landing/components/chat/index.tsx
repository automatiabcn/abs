/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Chat UI atoms (single-file barrel for /panel/chat).
// Components: ProviderChip, MetaPills, MetaSidebar, ToolCallCard, Markdown,
// MessageBubble, MessageInput (with SlashCommandPalette), ChatSidebar,
// EmptyState. All "use client" — they import hooks and react-markdown.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowDownToLine,
  ArrowUp,
  Bot,
  Clock,
  Layers,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  StopCircle,
  Trash2,
  User,
  Wrench,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type {
  ChatMessage,
  MetaEvent,
  SessionListItem,
  ToolCall,
} from "@/lib/chat-stream";
import {
  CATEGORY_ICONS,
  HERO_PROMPT_IDS,
  PROMPT_CATEGORIES,
  PROMPTS,
  type PromptItem,
  type PromptLang,
} from "@/lib/prompt-library";

// ───── ProviderChip ─────────────────────────────────────────────────────

const PROVIDER_PALETTE: Record<
  string,
  { label: string; tone: string; icon: typeof Layers }
> = {
  groq: { label: "Groq", tone: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30", icon: Layers },
  cerebras: { label: "Cerebras", tone: "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30", icon: Layers },
  cloudflare: { label: "Cloudflare", tone: "bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30", icon: Layers },
  gemini: { label: "Gemini", tone: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30", icon: Layers },
  cohere: { label: "Cohere", tone: "bg-pink-500/15 text-pink-700 dark:text-pink-300 border-pink-500/30", icon: Layers },
  "anthropic-mock": {
    label: "Anthropic mock",
    tone: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
    icon: Sparkles,
  },
  none: { label: "Not configured", tone: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30", icon: Layers },
};

export function ProviderChip({
  provider,
  mock,
}: {
  provider?: string;
  mock?: boolean;
}) {
  if (!provider) return null;
  const meta = PROVIDER_PALETTE[provider] ?? {
    label: provider,
    tone: "bg-muted text-foreground border-border",
    icon: Layers,
  };
  const Icon = meta.icon;
  return (
    <span
      data-test="provider-chip"
      data-provider={provider}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        meta.tone,
      )}
    >
      <Icon className="h-3 w-3" />
      {meta.label}
      {mock && (
        <span className="rounded bg-amber-500/30 px-1 text-[9px] uppercase text-amber-200">
          mock
        </span>
      )}
    </span>
  );
}

// ───── MetaPills (small inline pills under assistant bubble) ────────────

export function MetaPills({
  tokensUsed,
  latencyMs,
}: {
  tokensUsed?: number;
  latencyMs?: number;
}) {
  if (tokensUsed == null && latencyMs == null) return null;
  return (
    <span className="inline-flex items-center gap-2 text-[11px] text-muted-foreground">
      {latencyMs != null && (
        <span className="inline-flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {latencyMs.toLocaleString()} ms
        </span>
      )}
      {tokensUsed != null && (
        <span className="inline-flex items-center gap-1">
          <Activity className="h-3 w-3" />
          {tokensUsed.toLocaleString()} tokens
        </span>
      )}
    </span>
  );
}

// ───── ToolCallCard ─────────────────────────────────────────────────────

const COMMAND_ACCENT: Record<string, string> = {
  rag: "border-l-indigo-500",
  workflow: "border-l-violet-500",
  code: "border-l-emerald-500",
  translate: "border-l-amber-500",
  analyze: "border-l-blue-500",
};

// Ask the agent for the server's status and it answers in a sentence — then
// dumps forty lines of raw JSON into the conversation underneath it. The
// customer did not ask for the payload; they asked a question, and the payload
// is how the answer was obtained.
//
// So the card states what the agent did, and keeps the evidence one click away
// for the person who wants to check it. It is a receipt, not the answer.
export function ToolCallCard({ call }: { call: ToolCall }) {
  const accent = COMMAND_ACCENT[call.name] ?? "border-l-primary";
  const lines = call.result ? call.result.split("\n").length : 0;
  return (
    <details
      data-test="tool-call-card"
      data-tool={call.name}
      className={cn(
        "group my-2 rounded-md border bg-background/40 text-xs",
        "border-l-4",
        accent,
      )}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 p-3 text-muted-foreground">
        <Wrench className="h-3 w-3 shrink-0" />
        <span className="font-mono font-semibold uppercase tracking-wider text-foreground">
          {call.name}
        </span>
        {call.args?.query && (
          <span className="truncate text-foreground/70">
            “{call.args.query}”
          </span>
        )}
        <span className="ml-auto shrink-0 text-[11px]">
          {call.result
            ? `${lines} line${lines === 1 ? "" : "s"} · show`
            : "running…"}
        </span>
      </summary>
      {call.result && (
        <pre className="mx-3 mb-3 max-h-72 overflow-auto rounded bg-muted/40 p-2 font-mono text-[11px] leading-relaxed text-foreground/90">
          {call.result}
        </pre>
      )}
    </details>
  );
}

// ───── Markdown ─────────────────────────────────────────────────────────

export function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-invert max-w-none text-sm leading-relaxed prose-pre:my-2 prose-pre:rounded-md prose-pre:bg-background/60 prose-pre:p-3 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          a: ({ ...props }) => (
            <a
              {...props}
              className="underline underline-offset-2 hover:text-primary"
              target="_blank"
              rel="noreferrer"
            />
          ),
        }}
      >
        {content || ""}
      </ReactMarkdown>
    </div>
  );
}

// ───── MessageBubble ────────────────────────────────────────────────────

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      data-test="chat-message"
      data-role={msg.role}
      // Whether the answer has arrived yet is only visible in the words
      // "Thinking…", which is enough for a person and nothing for anything else.
      // A screen reader gets `aria-busy`, and the scenario suite — which reads
      // this bubble to decide what the product replied — gets a state instead of
      // having to guess from the text. It was guessing wrong: it settled on
      // "Thinking…" as the answer and passed a nine-character reply as a real one.
      data-pending={msg.role === "assistant" && msg.content === "" ? "true" : "false"}
      aria-busy={msg.role === "assistant" && msg.content === ""}
      className={cn(
        "flex w-full gap-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[78%] rounded-2xl border px-4 py-3 shadow-sm",
          isUser
            ? "border-primary/30 bg-primary/10 text-foreground"
            : "border-border bg-card/70 backdrop-blur",
        )}
      >
        {msg.role === "assistant" && msg.content === "" ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
            Thinking…
          </div>
        ) : (
          // The answer, addressable on its own. What the model *said* and what it
          // cited are different claims, and a test that cannot tell them apart
          // cannot catch an answer taken from the wrong source.
          <div data-test="chat-message-text">
            <Markdown content={msg.content} />
          </div>
        )}
        {msg.toolCalls?.map((tc, i) => (
          <ToolCallCard key={i} call={tc} />
        ))}
        {!isUser && msg.citations && msg.citations.length > 0 && (
          <div
            className="mt-2 border-t border-border/50 pt-2"
            data-test="chat-citations"
          >
            <div className="mb-1 text-xs font-medium text-muted-foreground">
              Sources
            </div>
            <ol className="space-y-1">
              {msg.citations.map((c, i) => (
                <li
                  key={c.chunk_id ?? i}
                  data-test="chat-citation"
                  className="text-xs text-muted-foreground"
                >
                  <span className="font-mono text-foreground">[{i + 1}]</span>{" "}
                  <span className="font-medium text-foreground">
                    {c.source || "source"}
                  </span>
                  {c.page != null && <span> · p.{c.page}</span>}
                  {c.relevance_score != null && (
                    <span className="ml-1 rounded bg-muted px-1 py-0.5 text-[10px]">
                      {(c.relevance_score * 100).toFixed(0)}%
                    </span>
                  )}
                  {c.excerpt && (
                    <div className="mt-0.5 line-clamp-2 opacity-80">
                      {c.excerpt}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
        {!isUser && (msg.provider || msg.tokensUsed != null || msg.latencyMs != null) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border/50 pt-2">
            <ProviderChip provider={msg.provider} mock={msg.mock} />
            <MetaPills tokensUsed={msg.tokensUsed} latencyMs={msg.latencyMs} />
          </div>
        )}
      </div>
      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <User className="h-4 w-4" />
        </div>
      )}
    </motion.div>
  );
}

// ───── SlashCommandPalette + MessageInput ───────────────────────────────

interface SlashCommand {
  cmd: string;
  desc: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: "/rag", desc: "Search your documents" },
  { cmd: "/workflow", desc: "Build and run a workflow" },
  { cmd: "/code", desc: "Write code (reviewed by a second model)" },
  { cmd: "/translate", desc: "Translate, then check the translation" },
  { cmd: "/analyze", desc: "Analyse from three angles, then synthesise" },
];

function SlashCommandPalette({
  query,
  onSelect,
}: {
  query: string;
  onSelect: (cmd: string) => void;
}) {
  const matches = useMemo(
    () =>
      SLASH_COMMANDS.filter((c) =>
        c.cmd.toLowerCase().includes(query.toLowerCase()),
      ),
    [query],
  );
  if (matches.length === 0) return null;
  return (
    <div
      data-test="slash-palette"
      className="absolute bottom-full left-0 mb-2 w-full max-w-md rounded-lg border border-border bg-popover p-1 shadow-lg"
    >
      {matches.map((c) => (
        <button
          key={c.cmd}
          type="button"
          onClick={() => onSelect(c.cmd)}
          className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
        >
          <span className="font-mono text-primary">{c.cmd}</span>
          <span className="text-xs text-muted-foreground">{c.desc}</span>
        </button>
      ))}
    </div>
  );
}

export function MessageInput({
  value,
  onChange,
  onSubmit,
  onAbort,
  disabled,
  isStreaming,
  agentMode,
  onToggleAgent,
  agentStep,
  placeholder = "Ask anything, or type / for a command…",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onAbort?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  /** Agent mode — the assistant may look things up before it answers. */
  agentMode?: boolean;
  onToggleAgent?: () => void;
  /** Which step the agent is on, while it runs. */
  agentStep?: number | null;
  placeholder?: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [showPalette, setShowPalette] = useState(false);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    setShowPalette(value.startsWith("/") && !value.includes(" "));
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="relative" data-test="message-input">
      {showPalette && (
        <SlashCommandPalette
          query={value}
          onSelect={(cmd) => {
            onChange(`${cmd} `);
            textareaRef.current?.focus();
            setShowPalette(false);
          }}
        />
      )}
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-card/70 p-2 shadow-sm focus-within:border-primary/50">
        {onToggleAgent && (
          <button
            type="button"
            onClick={onToggleAgent}
            disabled={isStreaming}
            aria-pressed={agentMode}
            data-test="agent-toggle"
            title={
              agentMode
                ? "Agent is on — it looks things up before answering, and asks you before it changes anything"
                : "Agent — let it look things up before answering"
            }
            className={
              agentMode
                ? "flex shrink-0 items-center gap-1.5 self-end rounded-full bg-primary-soft px-2.5 py-1.5 text-xs font-medium text-primary transition-colors"
                : "flex shrink-0 items-center gap-1.5 self-end rounded-full px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-surface-raised hover:text-foreground"
            }
          >
            <Sparkles className="h-3.5 w-3.5" />
            {/* The step counter is the whole reason this label is live: an agent
                run takes seconds and several provider calls, and a still spinner
                through that reads as a hang. */}
            {agentMode && agentStep ? `Step ${agentStep}` : "Agent"}
          </button>
        )}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={placeholder}
          className="flex-1 resize-none border-0 bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        {isStreaming ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onAbort}
            aria-label="Stop"
            data-testid="chat-abort"
          >
            <StopCircle className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            aria-label="Send message"
            data-testid="chat-send"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        )}
      </div>
      <div className="mt-1 px-2 text-[11px] text-muted-foreground">
        Enter to send · Shift+Enter for a new line · / for commands
      </div>
    </div>
  );
}

// ───── ChatSidebar (left rail) ──────────────────────────────────────────

export function ChatSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  isLoading,
  onShowPrompts,
}: {
  sessions: SessionListItem[];
  activeId?: number;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  isLoading: boolean;
  // Phase B (2026-05-08) — chat sidebar exposes a footer button that
  // toggles the right-side PromptLibrary drawer in the parent. Optional
  // so non-chat consumers (e.g. workflow chat panel) keep working.
  onShowPrompts?: () => void;
}) {
  const [filter, setFilter] = useState("");
  const visible = useMemo(
    () =>
      sessions.filter((s) =>
        s.title.toLowerCase().includes(filter.toLowerCase()),
      ),
    [sessions, filter],
  );
  return (
    <aside
      data-test="chat-sidebar"
      className="hidden w-72 shrink-0 flex-col border-r border-border bg-card/40 p-3 lg:flex"
    >
      <Button
        type="button"
        onClick={onNew}
        className="mb-3 justify-start gap-2"
        data-test="chat-new"
      >
        <Plus className="h-4 w-4" />
        New chat
      </Button>
      <div className="relative mb-2">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search conversations…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="pl-7 text-sm"
        />
      </div>
      <div className="-mx-1 flex-1 overflow-y-auto px-1">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            No conversations yet.
          </p>
        ) : (
          <ul className="space-y-1">
            {visible.map((s) => (
              <li key={s.id}>
                <div
                  className={cn(
                    "group flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors",
                    s.id === activeId
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(s.id)}
                    className="flex flex-1 items-center gap-2 truncate text-left"
                    data-test="chat-session-link"
                    data-session-id={s.id}
                  >
                    <MessageSquare className="h-4 w-4 shrink-0" />
                    <span className="truncate">{s.title}</span>
                  </button>
                  <span className="text-[10px] text-muted-foreground">
                    {s.message_count}
                  </span>
                  <button
                    type="button"
                    onClick={() => onDelete(s.id)}
                    className="opacity-0 transition-opacity group-hover:opacity-100"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-rose-400 hover:text-rose-700 dark:text-rose-300" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {onShowPrompts && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onShowPrompts}
          data-test="chat-prompts-toggle"
          className="mt-3 justify-start gap-2 border-t border-border/60 pt-3 text-sm text-muted-foreground hover:text-foreground"
        >
          <Sparkles className="h-4 w-4 text-primary" />
          Prompt library
        </Button>
      )}
    </aside>
  );
}

// ───── MetaSidebar (right rail) ─────────────────────────────────────────

export function MetaSidebar({ meta }: { meta: MetaEvent | null }) {
  return (
    <aside
      data-test="chat-meta"
      className="hidden w-80 shrink-0 flex-col border-l border-border bg-card/40 p-4 xl:flex"
    >
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Details
      </h3>
      {!meta ? (
        <p className="text-sm text-muted-foreground">
          Once you ask something, this shows who answered and what it cost.
        </p>
      ) : (
        <div className="space-y-4">
          <Card className="bg-background/60">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                Provider
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProviderChip provider={meta.provider} mock={meta.mock} />
            </CardContent>
          </Card>
          <Card className="bg-background/60">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                Performance
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Response time</span>
                <span className="font-mono">
                  {meta.latencyMs.toLocaleString()} ms
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tokens</span>
                <span className="font-mono">
                  {meta.tokensUsed.toLocaleString()}
                </span>
              </div>
            </CardContent>
          </Card>
          {meta.fallbackChain.length > 0 && (
            <Card className="bg-background/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  Providers tried
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs">
                {meta.fallbackChain.map((p, i) => (
                  <div
                    key={`${p}-${i}`}
                    className="flex items-center gap-2"
                  >
                    <span className="font-mono text-muted-foreground">
                      {i + 1}.
                    </span>
                    <ProviderChip provider={p} />
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </aside>
  );
}

// ───── EmptyState ───────────────────────────────────────────────────────

// Phase B (2026-05-08) — empty chat state now surfaces eight hero prompts
// (one per category from lib/prompt-library.ts) plus a "show all" CTA
// that opens the right-side PromptLibrary drawer. Replaces the four
// hardcoded openers from an earlier polish pass; the older neutral openers were
// fine but did not scale and offered no discoverability for the 48
// curated prompts the library now ships with.
const EMPTY_STATE_COPY: Record<
  PromptLang,
  { title: string; subtitle: string; cta: string; tip: string }
> = {
  en: {
    title: "Ask anything",
    subtitle:
      "If one provider is down, the next one answers. Type / to run a command.",
    cta: "Browse all 48 prompts",
    tip: "Tip: open the command palette with ⌘K",
  },
  tr: {
    title: "Ask anything",
    subtitle:
      "If one provider is down, the next one answers. Type / to run a command.",
    cta: "Browse all 48 prompts",
    tip: "Tip: open the command palette with ⌘K",
  },
  es: {
    title: "Empieza a hablar con la IA",
    subtitle:
      "El cascade router conmuta entre 6 proveedores. Los comandos slash invocan herramientas MCP.",
    cta: "Ver los 48 prompts",
    tip: "Sugerencia: abre la paleta de comandos con ⌘K",
  },
};

export function EmptyState({
  onPick,
  lang = "en",
  onShowAll,
}: {
  onPick: (prompt: string) => void;
  // Default "en" so existing callers without the prop fall back
  // to English copy. ChatClient passes the customer's preferred lang.
  lang?: PromptLang;
  // Clicking the CTA opens the PromptLibrary drawer. Optional
  // so non-chat consumers (workflow chat panel) keep their old behaviour.
  onShowAll?: () => void;
}) {
  const heroes = useMemo(
    () => HERO_PROMPT_IDS.map((id) => PROMPTS.find((p) => p.id === id)).filter(
      (p): p is PromptItem => Boolean(p),
    ),
    [],
  );
  const copy = EMPTY_STATE_COPY[lang];
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
      data-test="chat-empty"
      className="mx-auto flex max-w-3xl flex-col items-center justify-center gap-6 px-6 py-16 text-center"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
        <Sparkles className="h-7 w-7 text-primary" />
      </div>
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{copy.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{copy.subtitle}</p>
      </div>
      <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {heroes.map((h) => {
          const cat = PROMPT_CATEGORIES.find((c) => c.id === h.category);
          const Icon = cat ? CATEGORY_ICONS[cat.iconName] : ArrowDownToLine;
          return (
            <button
              key={h.id}
              type="button"
              onClick={() => onPick(h.prompt[lang])}
              data-test="chat-sample-prompt"
              data-prompt-id={h.id}
              className="rounded-xl border border-border bg-card/60 p-4 text-left text-sm transition-colors hover:border-primary/50 hover:bg-card"
            >
              <div className="mb-1 flex items-center gap-2 text-xs font-medium text-primary">
                <Icon className="h-3.5 w-3.5" />
                {h.title[lang]}
              </div>
              <div className="line-clamp-3 text-xs text-muted-foreground">
                {h.description[lang]}
              </div>
            </button>
          );
        })}
      </div>
      {onShowAll && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onShowAll}
          data-test="chat-empty-show-all"
          className="gap-2"
        >
          <Sparkles className="h-4 w-4 text-primary" />
          {copy.cta}
        </Button>
      )}
      <Badge variant="outline" className="text-xs">
        {copy.tip}
      </Badge>
    </motion.div>
  );
}
