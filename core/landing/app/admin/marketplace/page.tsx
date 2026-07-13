/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/marketplace` — the plugin catalogue this server actually offers.
//
// There used to be a hardcoded list of ten manifests rendered whenever the
// catalogue request failed. They looked exactly like real plugins, they carried
// permission lists a person would read and trust, and their Install buttons
// worked. The page's own promise is that "every plugin shows you exactly what it
// can reach before you install it" — over an invented catalogue that is not a
// feature, it is a fabrication with a consent dialog attached.
"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Store } from "lucide-react";

import MarketplacePanel from "@/components/MarketplacePanel";
import { Skeleton } from "@/components/ui/skeleton";
import { type PluginManifest } from "@/lib/marketplace";

interface AuthMe {
  email: string;
  role?: string;
}

async function fetchPluginsLive(): Promise<PluginManifest[] | null> {
  try {
    const res = await fetch("/api/marketplace/plugins", {
      cache: "no-store",
      credentials: "include",
    });
    if (!res.ok) return null;
    return (await res.json()) as PluginManifest[];
  } catch {
    return null;
  }
}

async function fetchMe(): Promise<AuthMe | null> {
  try {
    const res = await fetch("/auth/me", { credentials: "include" });
    if (!res.ok) return null;
    return (await res.json()) as AuthMe;
  } catch {
    return null;
  }
}

export default function MarketplacePage() {
  const [plugins, setPlugins] = useState<PluginManifest[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([fetchPluginsLive(), fetchMe()]).then(([live, me]) => {
      if (!active) return;
      // A failed catalogue request used to render ten plugins that do not exist
      // on this server — with working Install buttons, under a heading promising
      // "every plugin shows you exactly what it can reach before you install it".
      // The catalogue is either the server's or it is nothing.
      if (live) setPlugins(live);
      else setFailed(true);
      // MP2 — auth'd panel users default to admin role unless explicitly set
      // otherwise. The legacy `x-abs-role` header path was never populated,
      // so the install button falsely disabled itself for everyone.
      setIsAdmin(me !== null && (me.role === undefined || me.role === "admin"));
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main
      data-page="admin-marketplace"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Store className="h-5 w-5 text-primary" />
          Plugin Marketplace
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Add providers, RAG sources, MCP tools and workflow templates to your
          server. Every plugin shows you exactly what it can reach before you
          install it.
        </p>
      </motion.header>

      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full" />
          ))}
        </div>
      ) : failed ? (
        <div
          data-test="marketplace-load-error"
          className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400"
        >
          We could not load the plugin catalogue from your server. Nothing is shown
          here rather than something we cannot install — reload once the server is
          reachable.
        </div>
      ) : (
        <MarketplacePanel initialPlugins={plugins ?? []} isAdmin={isAdmin} />
      )}
    </main>
  );
}
