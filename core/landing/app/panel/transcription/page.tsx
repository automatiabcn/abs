/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// S20.6 — /panel/transcription: WebRTC mic → 5s chunked POST /v1/transcribe/stream → segments
// TR2 mic permission Modal + TR3 real-time waveform + TR6 empty state.
"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Waveform } from "@/components/panel/Waveform";
import { DEFAULT_VOICE_ID } from "@/lib/tts";

interface Segment {
  speaker_id: string;
  start: number;
  end: number;
  text: string;
}

const CHUNK_INTERVAL_MS = 5000;
const SPEAKER_COLORS: Record<string, string> = {
  spk_0: "#0ea5e9",
  spk_1: "#10b981",
  spk_2: "#f59e0b",
  spk_3: "#ef4444",
  spk_4: "#8b5cf6",
  spk_5: "#14b8a6",
};

function srtTimestamp(sec: number): string {
  const h = String(Math.floor(sec / 3600)).padStart(2, "0");
  const m = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
  const s = String(Math.floor(sec % 60)).padStart(2, "0");
  const ms = String(Math.floor((sec % 1) * 1000)).padStart(3, "0");
  return `${h}:${m}:${s},${ms}`;
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export default function TranscriptionPanel() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [recording, setRecording] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("Ready");
  const [error, setError] = useState<string | null>(null);
  const [voice, setVoice] = useState<string>(DEFAULT_VOICE_ID);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cumulativeOffset = useRef<number>(0);
  const reducedMotion = useRef<boolean>(false);

  // pre-explanation gate before getUserMedia
  const [permissionOpen, setPermissionOpen] = useState(false);
  const [permissionAcknowledged, setPermissionAcknowledged] = useState(false);
  // keep a ref-mirror of the active stream so Waveform can subscribe
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    reducedMotion.current = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
  }, []);

  // First run shows the data-handling modal; once acknowledged we go
  // straight to capture on subsequent sessions in the same tab.
  const requestStart = () => {
    if (!permissionAcknowledged) {
      setPermissionOpen(true);
      return;
    }
    void start();
  };

  const acknowledgeAndStart = () => {
    setPermissionAcknowledged(true);
    setPermissionOpen(false);
    void start();
  };

  const start = async () => {
    setError(null);
    cumulativeOffset.current = 0;
    setSegments([]);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser cannot access the microphone. Try Chrome, Edge or Safari.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setActiveStream(stream);
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return;
        const form = new FormData();
        form.append("audio", event.data, "chunk.webm");
        try {
          const res = await fetch("/v1/transcribe/stream", {
            method: "POST",
            body: form,
            credentials: "include",
          });
          if (!res.ok) {
            setStatusMessage(`Server returned HTTP ${res.status}`);
            return;
          }
          const data = await res.json();
          const offset = cumulativeOffset.current;
          const incoming: Segment[] = (data.segments ?? []).map((s: Segment) => ({
            ...s,
            start: s.start + offset,
            end: s.end + offset,
          }));
          if (incoming.length > 0) {
            cumulativeOffset.current = incoming[incoming.length - 1].end;
            setSegments((prev) => [...prev, ...incoming]);
          }
        } catch (exc) {
          setStatusMessage(`Upload failed: ${(exc as Error).message}`);
        }
      };
      recorder.onerror = (event) => {
        setError(`Recording stopped unexpectedly: ${(event as Event).type}`);
      };
      recorderRef.current = recorder;
      recorder.start(CHUNK_INTERVAL_MS);
      setRecording(true);
      setStatusMessage("Recording — sending audio every 5 seconds…");
    } catch (exc) {
      setError(`Could not open the microphone: ${(exc as Error).message}`);
    }
  };

  const stop = () => {
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
    streamRef.current = null;
    setActiveStream(null);
    setRecording(false);
    setStatusMessage("Ready");
  };

  useEffect(() => () => stop(), []);

  const reSynthesize = async (text: string) => {
    try {
      const res = await fetch("/v1/tts/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text, voice }),
      });
      if (!res.ok) {
        setError(`Could not play this line back: HTTP ${res.status}`);
        return;
      }
      const buf = await res.arrayBuffer();
      const url = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (exc) {
      setError(`Could not play this line back: ${(exc as Error).message}`);
    }
  };

  const exportJson = () =>
    downloadBlob(
      JSON.stringify({ segments, exported_at: new Date().toISOString() }, null, 2),
      "transcript.json",
      "application/json",
    );

  const exportSrt = () =>
    downloadBlob(
      segments
        .map(
          (s, i) =>
            `${i + 1}\n${srtTimestamp(s.start)} --> ${srtTimestamp(s.end)}\n${s.text}\n`,
        )
        .join("\n"),
      "transcript.srt",
      "text/plain;charset=utf-8",
    );

  const exportTxt = () =>
    downloadBlob(
      segments.map((s) => s.text).join("\n"),
      "transcript.txt",
      "text/plain;charset=utf-8",
    );

  const speakerColor = (id: string) =>
    SPEAKER_COLORS[id] ?? "#71717a";

  return (
    <main
      data-page="panel-transcription"
      className="mx-auto max-w-3xl px-6 py-12 text-foreground"
    >
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Live Transcription</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Turn on your microphone and the transcript builds as you speak, with
          each speaker labelled. Play any line back in the voice you choose.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        {recording ? (
          <button
            type="button"
            onClick={stop}
            className="rounded bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={requestStart}
            data-test="transcription-start"
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Start
          </button>
        )}
        <span
          aria-live="polite"
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
            recording
              ? "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300"
              : error
                ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              recording
                ? "animate-pulse bg-rose-400"
                : error
                  ? "bg-amber-400"
                  : "bg-emerald-400"
            }`}
          />
          {statusMessage}
        </span>
        <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          Playback voice:
          <select
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="tr_TR-fettah-medium">tr_TR (Fettah)</option>
            <option value="en_US-amy-medium">en_US (Amy)</option>
            <option value="es_ES-davefx-medium">es_ES (DaveFX)</option>
          </select>
        </label>
      </div>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200"
        >
          {error}
        </p>
      )}

      {/* real-time waveform */}
      <div
        data-test="transcription-waveform-wrap"
        className="mb-6 rounded-md border border-border bg-card/40 p-3"
      >
        <Waveform stream={activeStream} active={recording} height={80} />
        <div className="mt-1 text-center text-[11px] text-muted-foreground">
          {recording
            ? "Microphone is live — audio is being transcribed as you speak"
            : "Press Start and your audio appears here"}
        </div>
      </div>

      <section className="mb-6 space-y-2">
        {segments.length === 0 ? (
          // 3-step illustration empty state
          <div
            data-test="transcription-empty"
            className="rounded-md border border-dashed border-border bg-card/30 p-6"
          >
            <p className="mb-3 text-center text-sm font-medium">
              Live transcription in three steps
            </p>
            <ol className="mx-auto grid max-w-lg grid-cols-1 gap-2 text-xs text-muted-foreground sm:grid-cols-3">
              <li className="rounded-md border border-border bg-background/40 p-3">
                <span className="font-mono text-primary">1.</span>{" "}
                Pick your playback voice, top right
              </li>
              <li className="rounded-md border border-border bg-background/40 p-3">
                <span className="font-mono text-primary">2.</span>{" "}
                Press <strong>Start</strong> and allow microphone access
              </li>
              <li className="rounded-md border border-border bg-background/40 p-3">
                <span className="font-mono text-primary">3.</span>{" "}
                Start talking — your words appear here as you go
              </li>
            </ol>
          </div>
        ) : (
          segments.map((seg, idx) => (
            <article
              key={idx}
              className="flex items-start gap-3 text-sm"
              style={
                reducedMotion.current
                  ? undefined
                  : { animation: "fade-in 200ms ease-out" }
              }
            >
              <span className="font-mono text-xs text-muted-foreground">
                {srtTimestamp(seg.start).slice(3, 8)}
              </span>
              <span
                className="rounded px-2 py-0.5 font-mono text-xs"
                style={{ background: speakerColor(seg.speaker_id), color: "#0a0e14" }}
              >
                {seg.speaker_id}
              </span>
              <span className="flex-1">{seg.text}</span>
              <button
                type="button"
                onClick={() => reSynthesize(seg.text)}
                className="text-xs text-muted-foreground underline hover:text-foreground"
              >
                Play
              </button>
            </article>
          ))
        )}
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Download transcript
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={exportJson}
            disabled={segments.length === 0}
            className="rounded border border-input px-3 py-1 hover:bg-accent disabled:opacity-50"
          >
            JSON
          </button>
          <button
            type="button"
            onClick={exportSrt}
            disabled={segments.length === 0}
            className="rounded border border-input px-3 py-1 hover:bg-accent disabled:opacity-50"
          >
            SRT
          </button>
          <button
            type="button"
            onClick={exportTxt}
            disabled={segments.length === 0}
            className="rounded border border-input px-3 py-1 hover:bg-accent disabled:opacity-50"
          >
            TXT
          </button>
        </div>
      </section>

      {/* mic permission pre-explanation */}
      <Dialog open={permissionOpen} onOpenChange={setPermissionOpen}>
        <DialogContent data-test="mic-permission-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Mic className="h-5 w-5 text-primary" />
              Microphone access
            </DialogTitle>
            <DialogDescription>
              Here&apos;s exactly what happens when you start.
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-2 text-sm">
            <li className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              Your audio is sent to your own server, a few seconds at a time,
              and turned into text there.
            </li>
            <li className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              Transcripts stay in your organization&apos;s database. They are
              never sent to an outside provider.
            </li>
            <li className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              The microphone stays on until you press <strong>Stop</strong>.
            </li>
          </ul>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPermissionOpen(false)}
              data-test="mic-permission-cancel"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={acknowledgeAndStart}
              data-test="mic-permission-accept"
            >
              Start recording
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
