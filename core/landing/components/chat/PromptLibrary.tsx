/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Phase B (2026-05-08) — searchable prompt-library drawer. Sits to the
// right of the chat main area; users open it from the chat sidebar
// or the empty-state CTA, browse 48 categorised prompts, pick one,
// and the prompt content lands in the chat input via the
// `onPick` callback provided by ChatClient. Self-contained: no global
// state, no router dependency.
"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Search, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CATEGORY_ICONS,
  PROMPT_CATEGORIES,
  PROMPTS,
  searchPrompts,
  type PromptItem,
  type PromptLang,
} from "@/lib/prompt-library";
import { cn } from "@/lib/utils";

const HEADER_TEXT: Record<PromptLang, string> = {
  en: "Prompt Library",
  tr: "Prompt Library",
  es: "Biblioteca de Prompts",
};

const SEARCH_PLACEHOLDER: Record<PromptLang, string> = {
  en: "Search prompts…",
  tr: "Search prompts…",
  es: "Buscar prompts…",
};

const NO_RESULTS: Record<PromptLang, string> = {
  en: "No prompts match that search.",
  tr: "No prompts match that search.",
  es: "Ningún prompt coincide con la búsqueda.",
};

export function PromptLibrary({
  lang = "en",
  onPick,
  onClose,
  defaultCategory = "founder",
}: {
  lang?: PromptLang;
  onPick: (prompt: string) => void;
  onClose?: () => void;
  defaultCategory?: string;
}) {
  const [openCat, setOpenCat] = useState<string | null>(defaultCategory);
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () => (search ? searchPrompts(search, lang) : PROMPTS),
    [search, lang],
  );

  return (
    <aside
      data-test="prompt-library"
      className="flex h-full w-80 flex-col border-l border-border bg-card/40"
    >
      <div className="flex items-center justify-between border-b border-border p-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-primary" />
          {HEADER_TEXT[lang]}
        </h3>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            data-test="prompt-library-close"
            aria-label="Close prompt library"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="border-b border-border p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            data-test="prompt-library-search"
            data-testid="prompt-library-search"
            placeholder={SEARCH_PLACEHOLDER[lang]}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-7 text-sm"
          />
        </div>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {search ? (
          filtered.length === 0 ? (
            <p
              data-test="prompt-library-empty"
              className="px-1 py-4 text-center text-xs text-muted-foreground"
            >
              {NO_RESULTS[lang]}
            </p>
          ) : (
            filtered.map((p) => (
              <PromptCard key={p.id} item={p} lang={lang} onPick={onPick} />
            ))
          )
        ) : (
          PROMPT_CATEGORIES.map((cat) => {
            const items = PROMPTS.filter((p) => p.category === cat.id);
            const Icon = CATEGORY_ICONS[cat.iconName];
            const open = openCat === cat.id;
            return (
              <div
                key={cat.id}
                data-test="prompt-library-category"
                data-category-id={cat.id}
                className="overflow-hidden rounded-lg border border-border"
              >
                <button
                  type="button"
                  data-test="prompt-library-category-toggle"
                  data-testid={`prompt-library-category-toggle-${cat.id}`}
                  data-category={cat.id}
                  onClick={() => setOpenCat(open ? null : cat.id)}
                  className="flex w-full items-center justify-between p-3 text-left transition-colors hover:bg-card/60"
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Icon className="h-4 w-4 text-primary" />
                    {cat.title[lang]}
                    <Badge variant="outline" className="text-[10px]">
                      {items.length}
                    </Badge>
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 transition-transform",
                      open && "rotate-180",
                    )}
                  />
                </button>
                {open && (
                  <div
                    data-test="prompt-library-category-content"
                    data-category={cat.id}
                    className="space-y-1.5 border-t border-border/60 bg-bg/40 p-2"
                  >
                    <p className="px-2 pb-1 text-[11px] text-muted-foreground">
                      {cat.description[lang]}
                    </p>
                    {items.map((p) => (
                      <PromptCard
                        key={p.id}
                        item={p}
                        lang={lang}
                        onPick={onPick}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

function PromptCard({
  item,
  lang,
  onPick,
}: {
  item: PromptItem;
  lang: PromptLang;
  onPick: (prompt: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(item.prompt[lang])}
      data-test="prompt-card"
      data-testid={`prompt-card-${item.id}`}
      data-prompt-id={item.id}
      className="w-full rounded-md border border-border/40 bg-card/60 p-2.5 text-left transition-colors hover:border-primary/40 hover:bg-card"
    >
      <div className="mb-0.5 text-xs font-medium">{item.title[lang]}</div>
      <div className="line-clamp-2 text-[11px] text-muted-foreground">
        {item.description[lang]}
      </div>
    </button>
  );
}
