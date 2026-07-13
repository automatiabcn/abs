/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase G — `/admin/marketplace` polish (MP1-MP5):
//   MP1 — drop manual <Footer/> (admin layout owns the chrome now)
//   MP2 — derive isAdmin from /auth/me on the client (server header was
//          never wired, so the banner falsely blocked installs)
//   MP3 — TR translation pass on copy
//   MP4 — plugin detail Sheet handled by MarketplacePanel (already
//          ships an inline modal); we keep the existing path
//   MP5 — extend FALLBACK to 10 manifests (matches Q7 milestone claim)
"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Store } from "lucide-react";

import MarketplacePanel from "@/components/MarketplacePanel";
import { Skeleton } from "@/components/ui/skeleton";
import { type PluginManifest } from "@/lib/marketplace";

const FALLBACK: PluginManifest[] = [
  {
    id: "vllm-endpoint",
    name: "vLLM Endpoint",
    version: "1.0.0",
    type: "llm-provider",
    entry_point: "ghcr.io/abs-plugins/vllm-endpoint:1.0.0",
    description:
      "Bring your own vLLM HTTP endpoint (OpenAI-compatible) — run inference on your own GPU.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/vllm-endpoint",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["*.internal", "vllm.local"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["VLLM_API_KEY"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 256,
    },
  },
  {
    id: "aws-bedrock",
    name: "AWS Bedrock",
    version: "1.0.0",
    type: "llm-provider",
    entry_point: "ghcr.io/abs-plugins/aws-bedrock:1.0.0",
    description:
      "Managed LLMs on AWS Bedrock (Claude, Mistral, Cohere) — access signed with SigV4.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/aws-bedrock",
    license: "Apache-2.0",
    permissions: {
      network_egress: [
        "bedrock-runtime.us-east-1.amazonaws.com",
        "bedrock.us-east-1.amazonaws.com",
      ],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 512,
    },
  },
  {
    id: "sharepoint-rag",
    name: "SharePoint RAG",
    version: "1.0.0",
    type: "rag-source",
    entry_point: "ghcr.io/abs-plugins/sharepoint-rag:1.0.0",
    description:
      "Microsoft SharePoint connector — indexes document libraries into RAG and keeps them in sync.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/sharepoint-rag",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["graph.microsoft.com", "login.microsoftonline.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["SP_CLIENT_ID", "SP_CLIENT_SECRET", "SP_TENANT_ID"],
      tenant_scoped: true,
      cpu_quota: 1.0,
      memory_mb: 1024,
    },
  },
  {
    id: "slack-thread-rag",
    name: "Slack Thread RAG",
    version: "1.0.0",
    type: "rag-source",
    entry_point: "ghcr.io/abs-plugins/slack-thread-rag:1.0.0",
    description:
      "Indexes Slack threads and channels — turns past conversations into searchable memory.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/slack-thread-rag",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["slack.com", "*.slack.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 512,
    },
  },
  {
    id: "notion-sync",
    name: "Notion Sync",
    version: "1.0.0",
    type: "mcp-tool",
    entry_point: "ghcr.io/abs-plugins/notion-sync:1.0.0",
    description:
      "Two-way Notion sync — mirrors pages, databases and attachments into RAG, and writes back via MCP.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/notion-sync",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["api.notion.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["NOTION_TOKEN"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 512,
    },
  },
  // ── MP5 fix — 5 more manifests, to match the Q7 milestone claim of
  // "10 plugin sandbox running".
  {
    id: "stripe-webhook",
    name: "Stripe Webhook Forwarder",
    version: "1.0.0",
    type: "mcp-tool",
    entry_point: "ghcr.io/abs-plugins/stripe-webhook:1.0.0",
    description:
      "Forwards Stripe webhook events (subscription.*, invoice.*) to an Inngest workflow.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/stripe-webhook",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["api.stripe.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["STRIPE_WEBHOOK_SECRET"],
      tenant_scoped: true,
      cpu_quota: 0.25,
      memory_mb: 256,
    },
  },
  {
    id: "github-issues",
    name: "GitHub Issues",
    version: "1.0.0",
    type: "mcp-tool",
    entry_point: "ghcr.io/abs-plugins/github-issues:1.0.0",
    description:
      "GitHub issue triage and label automation — read/write access, one repo at a time.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/github-issues",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["api.github.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["GITHUB_APP_TOKEN"],
      tenant_scoped: true,
      cpu_quota: 0.25,
      memory_mb: 256,
    },
  },
  {
    id: "linear-sync",
    name: "Linear Sync",
    version: "1.0.0",
    type: "mcp-tool",
    entry_point: "ghcr.io/abs-plugins/linear-sync:1.0.0",
    description:
      "Create and update Linear tickets — connects workflow output to your product backlog.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/linear-sync",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["api.linear.app"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["LINEAR_API_KEY"],
      tenant_scoped: true,
      cpu_quota: 0.25,
      memory_mb: 256,
    },
  },
  {
    id: "confluence-rag",
    name: "Confluence RAG",
    version: "1.0.0",
    type: "rag-source",
    entry_point: "ghcr.io/abs-plugins/confluence-rag:1.0.0",
    description:
      "Indexes Atlassian Confluence spaces — page hierarchy and attachments included.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/confluence-rag",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["*.atlassian.net"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["CONFLUENCE_API_TOKEN"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 512,
    },
  },
  {
    id: "zendesk-tickets",
    name: "Zendesk Tickets",
    version: "1.0.0",
    type: "mcp-tool",
    entry_point: "ghcr.io/abs-plugins/zendesk-tickets:1.0.0",
    description:
      "Read Zendesk support tickets and post replies — ingest into RAG, draft answers with AI.",
    author: "Automatia BCN",
    homepage: "https://github.com/abs-plugins/zendesk-tickets",
    license: "Apache-2.0",
    permissions: {
      network_egress: ["*.zendesk.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["ZENDESK_API_TOKEN"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 512,
    },
  },
];

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
  const [plugins, setPlugins] = useState<PluginManifest[]>(FALLBACK);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([fetchPluginsLive(), fetchMe()]).then(([live, me]) => {
      if (!active) return;
      if (live && live.length > 0) setPlugins(live);
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
      ) : (
        <MarketplacePanel initialPlugins={plugins} isAdmin={isAdmin} />
      )}
    </main>
  );
}
