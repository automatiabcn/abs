// Q9 Phase C / TR3 — real-time microphone waveform via Web Audio API
// AnalyserNode + Canvas. Drives 60fps repaint while a MediaStream is
// flowing; fades to a flat baseline when `stream` is null. The
// component is purely visual — capture is owned by the caller.
"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface WaveformProps {
  stream: MediaStream | null;
  active?: boolean;
  height?: number;
  /** Tailwind-friendly stroke color (uses currentColor by default). */
  className?: string;
}

export function Waveform({
  stream,
  active = true,
  height = 72,
  className,
}: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cancelled = false;

    const setupAudio = async () => {
      if (!stream) return;
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AudioCtx) return;
      const audioCtx = new AudioCtx();
      audioCtxRef.current = audioCtx;
      const src = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      src.connect(analyser);
      analyserRef.current = analyser;
    };

    void setupAudio();

    const dpr = window.devicePixelRatio || 1;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    };
    resize();
    const obs = new ResizeObserver(() => {
      // Reset transform before re-applying scale on resize.
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      resize();
    });
    obs.observe(canvas);

    const draw = () => {
      if (cancelled) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);

      const analyser = analyserRef.current;
      if (analyser && active) {
        const buf = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(buf);
        ctx.lineWidth = 2;
        ctx.strokeStyle = "currentColor";
        ctx.beginPath();
        const slice = w / buf.length;
        for (let i = 0; i < buf.length; i++) {
          const v = buf[i] / 128.0; // 0..2, 1 = silence
          const y = (v * h) / 2;
          if (i === 0) ctx.moveTo(i * slice, y);
          else ctx.lineTo(i * slice, y);
        }
        ctx.stroke();
      } else {
        // Flat baseline when idle.
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(150,150,150,0.4)";
        ctx.beginPath();
        ctx.moveTo(0, h / 2);
        ctx.lineTo(w, h / 2);
        ctx.stroke();
      }
      rafRef.current = window.requestAnimationFrame(draw);
    };
    rafRef.current = window.requestAnimationFrame(draw);

    return () => {
      cancelled = true;
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
      obs.disconnect();
      analyserRef.current?.disconnect();
      analyserRef.current = null;
      void audioCtxRef.current?.close();
      audioCtxRef.current = null;
    };
  }, [stream, active]);

  return (
    <canvas
      ref={canvasRef}
      data-test="waveform"
      data-active={active}
      style={{ height }}
      className={cn(
        "w-full text-primary",
        active ? "opacity-100" : "opacity-50",
        className,
      )}
    />
  );
}
