export type PluginType = "llm-provider" | "rag-source" | "mcp-tool" | "workflow-template";

export interface PluginPermissions {
  network_egress: string[];
  filesystem_read: string[];
  filesystem_write: string[];
  secrets: string[];
  tenant_scoped: boolean;
  cpu_quota: number;
  memory_mb: number;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  type: PluginType;
  entry_point: string;
  description: string;
  author: string;
  homepage?: string;
  license: string;
  permissions: PluginPermissions;
}

export const PLUGIN_TYPE_LABEL: Record<PluginType, string> = {
  "llm-provider": "LLM Provider",
  "rag-source": "RAG Source",
  "mcp-tool": "MCP Tool",
  "workflow-template": "Workflow Template",
};

export const PLUGIN_TYPE_ORDER: PluginType[] = [
  "llm-provider",
  "rag-source",
  "mcp-tool",
  "workflow-template",
];
