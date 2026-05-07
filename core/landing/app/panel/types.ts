/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// R70 (S8) — shared between server `page.tsx` and the client island
// `PanelHomeClient.tsx`. The two halves agree on the shape of each of
// the three first-paint endpoints (`/v1/panel/tools`,
// `/v1/system/quota_status`, `/v1/panel/cascade/recent`) plus the
// MOCK fallback used when the call fails (auth gone, transport down,
// etc.) — same fallback semantics as the pre-R70 client `useQuery`.

export interface ToolsResponse {
  total?: number;
  category_counts?: Record<string, number>;
}

export interface QuotaSlice {
  used: number;
  limit: number;
  percent: number;
  label: string;
}

export interface QuotaResponse {
  claude_plus: QuotaSlice;
  free_providers?: Record<string, QuotaSlice>;
}

export interface CascadePoint {
  ts: string;
  count: number;
}

export interface CascadeResponse {
  count?: number;
  providers_active?: number;
  timeseries?: CascadePoint[];
}

export const MOCK_TOOLS: ToolsResponse = {
  total: 0,
  category_counts: {},
};

export const MOCK_QUOTA: QuotaResponse = {
  claude_plus: { used: 0, limit: 0, percent: 0, label: "claude_plus" },
};

export const MOCK_CASCADE: CascadeResponse = {
  count: 0,
  providers_active: 0,
  timeseries: [],
};
