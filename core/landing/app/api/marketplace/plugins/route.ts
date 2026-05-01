// P1 / S19-close — Next.js proxy → backend /v1/marketplace/plugins
// Returns the plugin list shaped for MarketplacePanel (PluginManifest[]).
import { NextResponse } from "next/server";

const BACKEND = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

interface BackendPlugin {
  id: string;
  name: string;
  version: string;
  summary: string;
  publisher: string;
  cosign_signature: string;
  sandbox?: { mem_mb?: number; cpu_cores?: number; egress_allowlist?: string[] };
  permissions?: string[];
  source?: string;
}

const TYPE_BY_ID: Record<string, string> = {
  "slack-receiver": "mcp-tool",
  "gmail-archiver": "rag-source",
  "linear-bridge": "mcp-tool",
  "notion-sync": "rag-source",
  "postgres-mirror": "rag-source",
};

export async function GET() {
  try {
    const upstream = await fetch(`${BACKEND}/v1/marketplace/plugins`, {
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json(
        { detail: `backend_status_${upstream.status}` },
        { status: upstream.status },
      );
    }
    const data = (await upstream.json()) as {
      plugins?: BackendPlugin[];
    };
    const manifests = (data.plugins ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      version: p.version,
      type: TYPE_BY_ID[p.id] ?? "mcp-tool",
      entry_point: `ghcr.io/abs-plugins/${p.id}:${p.version}`,
      description: p.summary,
      author: p.publisher,
      homepage: p.source
        ? `https://${p.source.replace(/^github:/, "github.com/")}`
        : undefined,
      license: "Apache-2.0",
      permissions: {
        network_egress: p.sandbox?.egress_allowlist ?? [],
        filesystem_read: ["/app/config"],
        filesystem_write: ["/tmp"],
        secrets: [],
        tenant_scoped: true,
        cpu_quota: p.sandbox?.cpu_cores ?? 0.5,
        memory_mb: p.sandbox?.mem_mb ?? 256,
      },
    }));
    return NextResponse.json(manifests);
  } catch (exc) {
    return NextResponse.json(
      { detail: `proxy_error: ${(exc as Error).message}` },
      { status: 502 },
    );
  }
}
