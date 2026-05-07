"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


// Q12-L18 (S6 R36) — register /sw.js for the /panel/* surface.
// The SW caches panel routes per strategy (chat = cache-first,
// dashboard = network-first w/ 3s timeout, rag = stale-while-
// revalidate). /v1/*, /_next/*, /auth/* always pass through. See
// public/sw.js for the full strategy contract.

import { useEffect } from "react";

export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NEXT_PUBLIC_DISABLE_SW === "1") return;

    const register = () => {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch(() => {
          // SW registration failures are non-fatal; the app must
          // still work without the cache layer.
        });
    };

    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  return null;
}
