// S20.6 — /panel/transcription: WebRTC mic → 5s chunked POST /v1/transcribe/stream → segments
"use client";

import { useEffect, useRef, useState } from "react";

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
  const [statusMessage, setStatusMessage] = useState<string>("Hazır");
  const [error, setError] = useState<string | null>(null);
  const [voice, setVoice] = useState<string>(DEFAULT_VOICE_ID);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cumulativeOffset = useRef<number>(0);
  const reducedMotion = useRef<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    reducedMotion.current = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
  }, []);

  const start = async () => {
    setError(null);
    cumulativeOffset.current = 0;
    setSegments([]);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Tarayıcı mikrofon erişimini desteklemiyor.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
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
            setStatusMessage(`Sunucu yanıtı: HTTP ${res.status}`);
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
          setStatusMessage(`Yayın hatası: ${(exc as Error).message}`);
        }
      };
      recorder.onerror = (event) => {
        setError(`Kayıt hatası: ${(event as Event).type}`);
      };
      recorderRef.current = recorder;
      recorder.start(CHUNK_INTERVAL_MS);
      setRecording(true);
      setStatusMessage("Kayıt ediliyor (5 saniyelik dilimler)…");
    } catch (exc) {
      setError(`Mikrofon açılamadı: ${(exc as Error).message}`);
    }
  };

  const stop = () => {
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
    streamRef.current = null;
    setRecording(false);
    setStatusMessage("Hazır");
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
        setError(`TTS başarısız: HTTP ${res.status}`);
        return;
      }
      const buf = await res.arrayBuffer();
      const url = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (exc) {
      setError(`TTS hatası: ${(exc as Error).message}`);
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
      className="mx-auto max-w-3xl px-6 py-12 text-zinc-900 dark:text-zinc-100"
    >
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Canlı Transkripsiyon</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Mikrofonu aç, 5 saniyelik dilimler WhisperX'e yollanır. Dilersen
          herhangi bir segmenti Piper ile yeniden seslendir.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        {recording ? (
          <button
            type="button"
            onClick={stop}
            className="rounded bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
          >
            Durdur
          </button>
        ) : (
          <button
            type="button"
            onClick={start}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Başlat
          </button>
        )}
        <span
          aria-live="polite"
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
            recording
              ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
              : error
                ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
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
        <label className="ml-auto flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
          Sesi:
          <select
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            className="rounded border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-900"
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

      <section className="mb-6 space-y-2">
        {segments.length === 0 ? (
          <p className="text-sm text-zinc-500">
            Henüz segment yok. Kayıt başlatıldığında 5 saniyede bir transkript
            buraya akar.
          </p>
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
              <span className="font-mono text-xs text-zinc-500">
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
                className="text-xs text-zinc-500 underline hover:text-zinc-900 dark:hover:text-zinc-100"
              >
                Seslendir
              </button>
            </article>
          ))
        )}
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Dışa aktar
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={exportJson}
            disabled={segments.length === 0}
            className="rounded border border-zinc-300 px-3 py-1 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            JSON
          </button>
          <button
            type="button"
            onClick={exportSrt}
            disabled={segments.length === 0}
            className="rounded border border-zinc-300 px-3 py-1 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            SRT
          </button>
          <button
            type="button"
            onClick={exportTxt}
            disabled={segments.length === 0}
            className="rounded border border-zinc-300 px-3 py-1 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            TXT
          </button>
        </div>
      </section>
    </main>
  );
}
