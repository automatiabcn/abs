/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Tremor ships its layout as Tailwind utility classes inside its own dist, and
// Tailwind does not scan node_modules unless told to. With this line missing, only
// the classes that happened to also appear in our own source were generated: the
// bar column of every chart kept its `space-y-1.5` while the value column lost its
// `mb-1.5`, so the two columns stepped 38px and 32px, and by the fifth row a number
// sat 24px away from the bar it belonged to.
//
// Nothing failed. No test went red, no console warned. The panel just quietly
// rendered its charts with half their CSS missing — which is why this is pinned
// here rather than trusted to review.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("tailwind content globs", () => {
  it("scans Tremor's dist, or every chart in the panel loses its layout", () => {
    const config = readFileSync(
      resolve(__dirname, "../tailwind.config.ts"),
      "utf8",
    );
    expect(config).toContain("node_modules/@tremor");
  });
});
