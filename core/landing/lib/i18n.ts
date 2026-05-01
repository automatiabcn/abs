/**
 * 023 — Landing i18n helper.
 *
 * Loads JSON locale dictionaries from `core/landing/locales/`.
 * Default lang `en`; supported `en|tr|es`. Missing keys → fallback to `en`.
 */

import enDict from "@/locales/en.json";
import trDict from "@/locales/tr.json";
import esDict from "@/locales/es.json";

export const SUPPORTED_LANGS = ["en", "tr", "es"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];
export const DEFAULT_LANG: Lang = "en";

const DICTS: Record<Lang, Record<string, string>> = {
  en: enDict as Record<string, string>,
  tr: trDict as Record<string, string>,
  es: esDict as Record<string, string>,
};

export function isLang(value: string | undefined | null): value is Lang {
  return !!value && (SUPPORTED_LANGS as readonly string[]).includes(value);
}

export function t(key: string, lang: Lang = DEFAULT_LANG): string {
  const dict = DICTS[lang] || DICTS[DEFAULT_LANG];
  return dict[key] ?? DICTS[DEFAULT_LANG][key] ?? key;
}

export function detectLangFromAcceptHeader(header: string | null | undefined): Lang {
  if (!header) return DEFAULT_LANG;
  for (const chunk of header.split(",")) {
    const tag = chunk.split(";")[0]?.trim().toLowerCase() ?? "";
    const prefix = tag.slice(0, 2);
    if (isLang(prefix)) return prefix;
  }
  return DEFAULT_LANG;
}
