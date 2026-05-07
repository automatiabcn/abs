/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-Q05 — chooses between the 3D R3F scene and the static SVG fallback.
// Rules:
//   - Mobile / tablet (< lg): always SVG (battery + perf).
//   - prefers-reduced-motion: always SVG.
//   - Slow connection (effectiveType 2g/slow-2g, or saveData): always SVG. (T-R03 #6)
//   - Otherwise: lazy-load HeroScene3D client-side only.
"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import HeroSvgFallback from "./HeroSvgFallback";

// `ssr: false` keeps Next from trying to render WebGL on the server.
const HeroScene3D = dynamic(() => import("./HeroScene3D"), {
  ssr: false,
  loading: () => null,
});

// T-R03 #6 — connection-aware: skip 3D on slow networks or save-data.
// `navigator.connection` (Network Information API) is only on Chromium-family;
// we feature-detect and treat absence as "fast" (no opinion).
type NetworkConnection = {
  effectiveType?: string;
  saveData?: boolean;
  addEventListener?: (e: string, fn: () => void) => void;
  removeEventListener?: (e: string, fn: () => void) => void;
};

function getConnection(): NetworkConnection | undefined {
  if (typeof navigator === "undefined") return undefined;
  return (navigator as Navigator & { connection?: NetworkConnection }).connection;
}

function isSlowConnection(): boolean {
  const conn = getConnection();
  if (!conn) return false;
  if (conn.saveData === true) return true;
  return conn.effectiveType === "slow-2g" || conn.effectiveType === "2g";
}

function useShould3D(): boolean {
  const [should, setShould] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mqDesktop = window.matchMedia("(min-width: 1024px)");
    const mqReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () =>
      setShould(mqDesktop.matches && !mqReduced.matches && !isSlowConnection());
    update();
    mqDesktop.addEventListener?.("change", update);
    mqReduced.addEventListener?.("change", update);
    const conn = getConnection();
    conn?.addEventListener?.("change", update);
    return () => {
      mqDesktop.removeEventListener?.("change", update);
      mqReduced.removeEventListener?.("change", update);
      conn?.removeEventListener?.("change", update);
    };
  }, []);
  return should;
}

export default function HeroVisual() {
  const should3D = useShould3D();
  if (should3D) return <HeroScene3D />;
  return <HeroSvgFallback />;
}
