/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// S20.5 — meeting detail: speakers + segments + summary
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import { formatDateTime } from "@/lib/format";

interface Segment {
  speaker_id: string;
  start: number;
  end: number;
  text: string;
}

interface MeetingDetail {
  id: number;
  filename: string;
  duration_sec: number;
  speaker_count: number;
  status: string;
  summary: string;
  error_message: string | null;
  speakers: Array<{ id: string; name: string }>;
  segments: Segment[];
  created_at: string;
}

const SPEAKER_COLORS = [
  "#0ea5e9", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#14b8a6", "#f97316", "#22c55e",
];

function fmtTime(s: number): string {
  const mm = Math.floor(s / 60);
  const ss = Math.floor(s % 60);
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = params?.id;
    if (!id) return;
    fetch(`/v1/meetings/${id}`, { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as MeetingDetail;
      })
      .then(setData)
      // Prefix the raw error with context so the user sees a
      // full sentence instead of a bare HTTP code.
      .catch((exc: Error) => setError(`Could not load this meeting: ${exc.message}`));
  }, [params?.id]);

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="alert" className="text-rose-700 dark:text-rose-300">
          {error}
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12 text-muted-foreground">
        Loading…
      </main>
    );
  }

  const speakerColor = (id: string) => {
    const idx = data.speakers.findIndex((s) => s.id === id);
    return SPEAKER_COLORS[Math.max(0, idx) % SPEAKER_COLORS.length];
  };
  // The transcript should read in the same names the legend uses ("Speaker 1"),
  // not the raw diarizer id ("spk_0"); fall back to the id if it isn't listed.
  const speakerName = (id: string) =>
    data.speakers.find((s) => s.id === id)?.name ?? id;

  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-foreground">
      <Link
        href="/panel/meetings"
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Meetings
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">{data.filename}</h1>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase text-muted-foreground">Length</dt>
          <dd className="font-mono">{fmtTime(data.duration_sec)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-muted-foreground">Speakers</dt>
          <dd className="font-mono">{data.speaker_count}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-muted-foreground">Status</dt>
          <dd className="font-mono">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-muted-foreground">Uploaded</dt>
          <dd className="font-mono">{formatDateTime(new Date(data.created_at), "en")}</dd>
        </div>
      </dl>

      {data.summary && (
        <section className="mt-6 rounded border border-border bg-muted/40 p-3 text-sm">
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Summary
          </h2>
          <p>{data.summary}</p>
        </section>
      )}

      {data.error_message && (
        <p
          role="alert"
          className="mt-4 rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200"
        >
          {data.error_message}
        </p>
      )}

      <section className="mt-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Speakers
        </h2>
        <ul className="flex flex-wrap gap-2">
          {data.speakers.map((sp) => (
            <li
              key={sp.id}
              className="flex items-center gap-2 rounded border border-border px-2 py-1 text-xs"
            >
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: speakerColor(sp.id) }}
              />
              {sp.name} <span className="font-mono text-muted-foreground">({sp.id})</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Transcript
        </h2>
        <ol className="space-y-2 text-sm">
          {data.segments.map((seg, idx) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="font-mono text-xs text-muted-foreground">
                {fmtTime(seg.start)}
              </span>
              <span
                className="rounded px-2 py-0.5 font-mono text-xs"
                style={{ background: speakerColor(seg.speaker_id), color: "#0a0e14" }}
              >
                {speakerName(seg.speaker_id)}
              </span>
              <span className="flex-1">{seg.text}</span>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
