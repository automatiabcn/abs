"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import { useEffect, useState } from "react";

interface DemoStatus {
  enabled: boolean;
  mock_providers: boolean;
  seed_version: string;
}

const KEY = "abs-demo-banner-dismissed";

export default function DemoBanner() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.sessionStorage.getItem(KEY) === "1") {
      setDismissed(true);
      return;
    }
    const ctrl = new AbortController();
    fetch("/v1/demo-mode/status", { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setStatus(data as DemoStatus);
      })
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  if (!status?.enabled || dismissed) return null;

  return (
    <div
      data-testid="demo-banner"
      role="region"
      aria-label="Demo mode notice"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: "linear-gradient(90deg,#1e57ac,#3b82f6)",
        color: "#fff",
        padding: "8px 16px",
        fontSize: 13,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
      }}
    >
      <span aria-hidden="true">🎬</span>
      <span>
        <strong>Demo Mode</strong> — sample data, not live customers (seed{" "}
        {status.seed_version}
        {status.mock_providers ? ", mock providers" : ""})
      </span>
      <button
        type="button"
        data-testid="demo-banner-dismiss"
        onClick={() => {
          window.sessionStorage.setItem(KEY, "1");
          setDismissed(true);
        }}
        style={{
          marginLeft: 8,
          background: "rgba(255,255,255,0.2)",
          border: 0,
          color: "#fff",
          borderRadius: 6,
          padding: "2px 8px",
          cursor: "pointer",
          fontSize: 12,
        }}
        aria-label="Dismiss demo banner"
      >
        Dismiss
      </button>
    </div>
  );
}
