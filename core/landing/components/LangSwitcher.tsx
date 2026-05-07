"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import * as React from "react";

import { type Lang, SUPPORTED_LANGS, isLang } from "@/lib/i18n";

interface LangSwitcherProps {
  current: Lang;
  onChange?: (lang: Lang) => void;
}

const LABELS: Record<Lang, string> = {
  en: "EN",
  tr: "TR",
  es: "ES",
};

export default function LangSwitcher({
  current,
  onChange,
}: LangSwitcherProps) {
  const handleSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    if (isLang(next)) {
      // Persist cookie
      if (typeof document !== "undefined") {
        document.cookie = `NEXT_LOCALE=${next}; max-age=${60 * 60 * 24 * 365}; path=/; samesite=lax`;
      }
      onChange?.(next);
      if (typeof window !== "undefined") {
        // Soft refresh — server re-renders with new lang via middleware/cookie
        window.location.reload();
      }
    }
  };

  return (
    <label className="text-xs text-muted-foreground" data-testid="lang-switcher">
      <span className="sr-only">Language</span>
      <select
        value={current}
        onChange={handleSelect}
        aria-label="Language"
        className="rounded border border-border bg-transparent px-2 py-1 text-xs"
      >
        {SUPPORTED_LANGS.map((lang) => (
          <option key={lang} value={lang}>
            {LABELS[lang]}
          </option>
        ))}
      </select>
    </label>
  );
}
