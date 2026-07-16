/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Live capture — manual-link bridge. Paste a Meet/Zoom/Teams link and a bot is
// dispatched to join and record it; the recording becomes a Meeting. Honest by
// construction: when no real recorder is connected the backend reports the job
// as simulated (recorder_live=false) and this surface says so, rather than
// implying a recording exists.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Video, Loader2, X } from "lucide-react";

interface CaptureJob {
  job_id: string;
  meeting_url: string;
  platform: string;
  title: string;
  status: string;
  bot_backend: string | null;
  recorder_live: boolean;
  estimated_cost_usd: number;
  error_message: string | null;
  scheduled_start: string | null;
  created_at: string | null;
  completed_at: string | null;
  meeting_id: number | null;
}

const PLATFORM_LABEL: Record<string, string> = {
  meet: "Google Meet",
  zoom: "Zoom",
  teams: "Microsoft Teams",
  other: "Meeting",
};

// One status → one badge. The wording matches what actually happened, so a
// simulated job never borrows the look of a real recording.
function statusStyle(status: string): { label: string; cls: string; pulse?: boolean } {
  switch (status) {
    case "queued":
    case "scheduled":
      return { label: "Scheduled", cls: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300" };
    case "joining":
      return { label: "Joining", cls: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300", pulse: true };
    case "recording":
      return { label: "Recording", cls: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300", pulse: true };
    case "transcribing":
      return { label: "Transcribing", cls: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300", pulse: true };
    case "done":
      return { label: "Done", cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" };
    case "failed":
      return { label: "Failed", cls: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300" };
    case "cancelled":
      return { label: "Cancelled", cls: "border-border bg-muted/40 text-muted-foreground" };
    default:
      return { label: status, cls: "border-border bg-muted/40 text-muted-foreground" };
  }
}

const TERMINAL = new Set(["done", "failed", "cancelled"]);

export function CaptureJobs() {
  const [jobs, setJobs] = useState<CaptureJob[]>([]);
  const [recorderAvailable, setRecorderAvailable] = useState<boolean | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/v1/capture/jobs", { credentials: "include" });
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data.jobs ?? []);
      setRecorderAvailable(Boolean(data.recorder_available));
    } catch {
      // A transient list failure isn't worth a banner; the next poll retries.
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
    // Poll while any job is still moving, so statuses advance without a refresh.
    pollRef.current = setInterval(load, 8000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  const submit = async () => {
    setError(null);
    const trimmed = url.trim();
    if (!trimmed) {
      setError("Paste the meeting link first.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/v1/capture/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ meeting_url: trimmed, title: title.trim() }),
      });
      if (res.status === 422) {
        setError("That doesn't look like a meeting link. Paste a Meet, Zoom or Teams URL.");
        return;
      }
      if (!res.ok) {
        setError(`Could not schedule the bot: HTTP ${res.status}`);
        return;
      }
      const job: CaptureJob = await res.json();
      setJobs((prev) => [job, ...prev]);
      setRecorderAvailable((prev) => (job.recorder_live ? true : prev ?? false));
      setUrl("");
      setTitle("");
    } catch (exc) {
      setError(`Could not schedule the bot: ${(exc as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = async (jobId: string) => {
    try {
      const res = await fetch(`/v1/capture/jobs/${jobId}/cancel`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        const updated: CaptureJob = await res.json();
        setJobs((prev) => prev.map((j) => (j.job_id === jobId ? updated : j)));
      }
    } catch {
      // best-effort; the poll will reconcile
    }
  };

  return (
    <section
      data-test="capture-jobs"
      className="mb-8 rounded-lg border border-border bg-card/40 p-4"
    >
      <div className="mb-1 flex items-center gap-2">
        <Video className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Send a bot to a meeting</h2>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Paste a Google Meet, Zoom or Teams link. A bot joins, records the call on
        your server, and files the transcript under Meetings — searchable
        alongside everything else.
      </p>

      {/* Honesty banner: without a connected recorder, jobs are simulated. */}
      {loaded && recorderAvailable === false && (
        <p
          data-test="capture-simulated-banner"
          className="mb-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-200"
        >
          No recorder is connected, so scheduled bots are <strong>simulated</strong>{" "}
          — a job is created but no audio is captured. Connect a self-hosted
          recorder (meetily / jitsi) or Recall.ai to capture meetings for real.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="url"
          inputMode="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !submitting) void submit();
          }}
          placeholder="https://meet.google.com/abc-defg-hij"
          data-test="capture-url"
          className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm"
        />
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (optional)"
          data-test="capture-title"
          className="rounded border border-input bg-background px-3 py-2 text-sm sm:w-48"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={submitting}
          data-test="capture-submit"
          className="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Send bot
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-xs text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}

      {/* Job list */}
      <div className="mt-4 space-y-2">
        {loaded && jobs.length === 0 ? (
          <p className="rounded border border-dashed border-border bg-background/40 px-3 py-4 text-center text-xs text-muted-foreground">
            No meetings scheduled for capture yet.
          </p>
        ) : (
          jobs.map((job) => {
            const s = statusStyle(job.status);
            return (
              <div
                key={job.job_id}
                data-test="capture-job-row"
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-border bg-background/40 px-3 py-2 text-sm"
              >
                <span className="font-medium">
                  {job.title || PLATFORM_LABEL[job.platform] || "Meeting"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {PLATFORM_LABEL[job.platform] ?? job.platform}
                </span>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${s.cls}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full bg-current ${s.pulse ? "animate-pulse" : ""}`}
                  />
                  {s.label}
                </span>
                {!job.recorder_live && (
                  <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
                    Simulated
                  </span>
                )}
                {job.recorder_live && job.estimated_cost_usd > 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    ~${job.estimated_cost_usd.toFixed(2)}
                  </span>
                )}
                {job.meeting_id != null && (
                  <a
                    href={`/admin/meetings?open=${job.meeting_id}`}
                    className="text-xs text-primary underline"
                  >
                    View meeting
                  </a>
                )}
                {job.error_message && (
                  <span className="text-[11px] text-rose-600 dark:text-rose-400">
                    {job.error_message}
                  </span>
                )}
                {!TERMINAL.has(job.status) && (
                  <button
                    type="button"
                    onClick={() => void cancel(job.job_id)}
                    data-test="capture-cancel"
                    className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    aria-label="Cancel capture"
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancel
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
