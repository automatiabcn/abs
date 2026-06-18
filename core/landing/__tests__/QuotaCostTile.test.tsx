// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// 3rd-eye audit regression. The quota page summed `slice.cost_usd`, but the
// backend QuotaSlice model (app/api/system/quota.py) never emits cost_usd, so
// the "Tahmini maliyet" tile rendered a constant $0.00. The tile now shows a
// real signal from the payload (threshold warning count). Lock it so the
// phantom cost field can't creep back in.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PAGE = readFileSync(
  resolve(__dirname, "../app/panel/quota/page.tsx"),
  "utf-8",
);

describe("panel/quota — no phantom cost field", () => {
  it("does not read slice.cost_usd (backend QuotaSlice never emits it)", () => {
    // No property access / type field — an explanatory comment may mention the
    // name, but the page must not *read* `.cost_usd` nor declare it on Slice.
    expect(PAGE).not.toContain(".cost_usd");
    expect(PAGE).not.toMatch(/cost_usd\??\s*:/);
  });

  it("surfaces a real threshold-warning count tile instead", () => {
    expect(PAGE).toContain("warningCount");
    expect(PAGE).toContain("Eşik uyarısı");
  });
});
