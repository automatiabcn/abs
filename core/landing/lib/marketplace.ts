/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

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

// Human-readable labels for the marketplace filter chips and plugin cards.
export const PLUGIN_TYPE_LABEL: Record<PluginType, string> = {
  "llm-provider": "LLM provider",
  "rag-source": "RAG source",
  "mcp-tool": "MCP tool",
  "workflow-template": "Workflow template",
};

export const PLUGIN_TYPE_ORDER: PluginType[] = [
  "llm-provider",
  "rag-source",
  "mcp-tool",
  "workflow-template",
];
