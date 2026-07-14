/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Locale-aware Intl wrappers for the landing surface.
//
// R58's `i18n-scope.test.ts` enforces "no hardcoded BCP-47 locale
// tags" on the landing surface. The follow-up risk is that someone
// reaching for `new Intl.NumberFormat("tr-TR")` or `(123).toLocaleString()`
// inline still ends up locale-forking by accident. This module is the
// single allowed home for landing-side numeric/date/plural rendering:
// every helper takes the active `lang` (Lang from lib/i18n.ts) and
// expands it to the right BCP-47 tag.
//
// Panel + admin + components/chat are TR-first by design and continue
// to call `(...).toLocaleString("tr-TR")` directly. R58's guard
// already exempts those directories.

import type { Lang } from "./i18n";

const LANG_TO_BCP47: Record<Lang, string> = {
  en: "en-US",
  tr: "tr-TR",
  es: "es-ES",
};

function bcp47(lang: Lang | string | undefined): string {
  if (lang && lang in LANG_TO_BCP47) return LANG_TO_BCP47[lang as Lang];
  return LANG_TO_BCP47.en;
}

/**
 * Locale-aware integer/decimal formatting.
 *   formatNumber(1234.56, "en") === "1,234.56"
 *   formatNumber(1234.56, "tr") === "1.234,56"
 *   formatNumber(1234.56, "es") === "1.234,56"
 *
 * `options` is an `Intl.NumberFormatOptions` passthrough so callers
 * can request a percent / currency / fixed-fraction form without
 * rebuilding the locale-tag table.
 */
export function formatNumber(
  n: number,
  lang: Lang | string | undefined,
  options?: Intl.NumberFormatOptions,
): string {
  if (!Number.isFinite(n)) return String(n);
  return new Intl.NumberFormat(bcp47(lang), options).format(n);
}

/**
 * Locale-aware date formatting (date-only by default).
 *   formatDate(new Date("2026-05-04"), "en") → "5/4/2026"
 *   formatDate(new Date("2026-05-04"), "tr") → "4.05.2026"
 *   formatDate(new Date("2026-05-04"), "es") → "4/5/2026"
 *
 * For dt+time use `formatDateTime` (below) or pass an
 * `Intl.DateTimeFormatOptions` object.
 */
export function formatDate(
  d: Date,
  lang: Lang | string | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(bcp47(lang), options).format(d);
}

/**
 * Locale-aware date+time formatting — wrapper around `formatDate`
 * that defaults to short date + numeric time.
 */
export function formatDateTime(
  d: Date,
  lang: Lang | string | undefined,
): string {
  return formatDate(d, lang, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

/**
 * Plural-aware label resolver. Turkish does not pluralize nouns by
 * count ("1 mesaj" / "5 mesaj"); English and Spanish do. Callers
 * pass the count and a map keyed by `Intl.PluralRules` categories
 * ("one", "other"); the helper picks the right value for the lang.
 *
 *   formatPlural(1, { one: "{n} message", other: "{n} messages" }, "en")
 *     === "1 message"
 *   formatPlural(5, { one: "{n} message", other: "{n} messages" }, "en")
 *     === "5 messages"
 *   formatPlural(5, { one: "{n} mesaj", other: "{n} mesaj" }, "tr")
 *     === "5 mesaj"
 *   formatPlural(0, { one: "{n} mensaje", other: "{n} mensajes" }, "es")
 *     === "0 mensajes"
 *
 * `{n}` is replaced with the locale-formatted count.
 */
export function formatPlural(
  count: number,
  forms: Partial<Record<Intl.LDMLPluralRule, string>>,
  lang: Lang | string | undefined,
): string {
  const tag = bcp47(lang);
  const rule = new Intl.PluralRules(tag).select(count);
  // `Intl.PluralRules` returns one of "zero" / "one" / "two" /
  // "few" / "many" / "other". Fall back through the chain so a
  // caller who only wired "one" + "other" still works for Spanish
  // (which sometimes selects "other" for 0).
  const template =
    forms[rule] ?? forms.other ?? forms.one ?? "";
  const formatted = formatNumber(count, lang);
  return template.replace("{n}", formatted);
}

// Exported for tests + future call-sites that need to know the
// exact BCP-47 mapping. Keep the table single-sourced here.
export const __test_only_bcp47 = bcp47;
