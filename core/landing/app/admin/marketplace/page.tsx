import { headers } from "next/headers";

import Footer from "@/components/Footer";
import MarketplacePanel from "@/components/MarketplacePanel";
import { type PluginManifest } from "@/lib/marketplace";

export const metadata = {
  title: "Plugin Marketplace — ABS Admin",
  robots: { index: false },
};

const FALLBACK: PluginManifest[] = [
  {
    id: "vllm-endpoint",
    name: "vLLM Endpoint",
    version: "1.0.0",
    type: "llm-provider",
    entry_point: "ghcr.io/abs-plugins/vllm-endpoint:1.0.0",
    description:
      "Bring-your-own vLLM HTTP endpoint (OpenAI-compatible) for on-prem GPU inference.",
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
      "AWS Bedrock managed LLM access (Anthropic Claude, Mistral, Cohere) using AWS SigV4.",
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
      "Microsoft SharePoint connector — index document libraries into ABS RAG with delta sync.",
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
      "Slack thread/channel ingestion for searchable conversation memory.",
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
      "Notion bidirectional sync — pages, databases, and inline attachments mirrored to ABS RAG and writable via MCP tool.",
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
];

async function loadPlugins(): Promise<PluginManifest[]> {
  const base = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";
  try {
    const r = await fetch(`${base}/api/marketplace/plugins`, { cache: "no-store" });
    if (!r.ok) throw new Error("non-ok");
    return (await r.json()) as PluginManifest[];
  } catch {
    return FALLBACK;
  }
}

export default async function Page() {
  const h = await headers();
  const isAdmin = h.get("x-abs-role") === "admin";
  const plugins = await loadPlugins();

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-3xl font-semibold text-zinc-900 dark:text-zinc-50">
        Plugin Marketplace
      </h1>
      <p className="mt-2 mb-8 max-w-2xl text-zinc-600 dark:text-zinc-300">
        Install and manage ABS plugins — LLM providers, RAG sources, MCP tools,
        and workflow templates. Each install requires explicit permission review.
      </p>
      <MarketplacePanel initialPlugins={plugins} isAdmin={isAdmin} />
      <div className="mt-16">
        <Footer />
      </div>
    </main>
  );
}
