/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Surface the 30-day KVKK / GDPR grace window so
// the customer can see the deletion countdown and cancel before the
// purge cron runs.
"use client";

import { useEffect, useState } from "react";

import { DEFAULT_LANG, type Lang, t } from "@/lib/i18n";

export type DeletionStatus =
  | { status: "none" }
  | { status: "scheduled"; scheduled_delete_at: string; days_remaining: number }
  | { status: "purged"; purged_at: string };

export type DeletionStatusBannerProps = {
  data: DeletionStatus;
  lang?: Lang;
  onCancel?: () => Promise<void> | void;
};

function _fmtDate(iso: string, lang: Lang): string {
  try {
    const d = new Date(iso);
    // Pass the short ISO language code; the runtime resolves the
    // regional subtag (tr→tr-TR, es→es-ES, en→en-US). Keeps the
    // landing surface free of hardcoded BCP-47 tags.
    return d.toLocaleDateString(lang, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function _interpolate(s: string, vars: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, key) => String(vars[key] ?? `{${key}}`));
}

export default function DeletionStatusBanner({
  data,
  lang = DEFAULT_LANG,
  onCancel,
}: DeletionStatusBannerProps) {
  const [busy, setBusy] = useState(false);

  if (data.status === "none") {
    return (
      <section
        aria-label={t("deletion.title", lang)}
        className="rounded-md border border-emerald-300 bg-emerald-50 p-4 text-emerald-900"
      >
        <h2 className="font-semibold">{t("deletion.title", lang)}</h2>
        <p className="mt-1 text-sm">{t("deletion.none", lang)}</p>
      </section>
    );
  }

  if (data.status === "purged") {
    return (
      <section
        aria-label={t("deletion.purged.title", lang)}
        className="rounded-md border border-border bg-muted/40 p-4 text-foreground"
      >
        <h2 className="font-semibold">{t("deletion.purged.title", lang)}</h2>
        <p className="mt-1 text-sm">
          {_interpolate(t("deletion.purged.body", lang), {
            date: _fmtDate(data.purged_at, lang),
          })}
        </p>
      </section>
    );
  }

  // scheduled
  return (
    <section
      aria-label={t("deletion.scheduled.title", lang)}
      role="alert"
      className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900"
    >
      <h2 className="font-semibold">{t("deletion.scheduled.title", lang)}</h2>
      <p className="mt-1 text-sm">
        {_interpolate(t("deletion.scheduled.body", lang), {
          date: _fmtDate(data.scheduled_delete_at, lang),
          days: data.days_remaining,
        })}
      </p>
      {onCancel ? (
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            try {
              setBusy(true);
              await onCancel();
            } finally {
              setBusy(false);
            }
          }}
          className="mt-3 inline-flex items-center rounded-md bg-amber-900 px-3 py-1.5 text-sm font-medium text-amber-50 disabled:opacity-60"
        >
          {t("deletion.cancel", lang)}
        </button>
      ) : null}
    </section>
  );
}

export function useDeletionStatus(): {
  data: DeletionStatus | null;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const [data, setData] = useState<DeletionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await fetch("/v1/me/account/deletion-status", {
        cache: "no-store",
      });
      if (!res.ok) {
        setError(`HTTP ${res.status}`);
        return;
      }
      setData((await res.json()) as DeletionStatus);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return { data, error, refresh };
}
