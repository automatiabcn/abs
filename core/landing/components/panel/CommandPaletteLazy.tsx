/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 21 / Faz D — client-side dynamic shim for CommandPalette.
// Server Components can't pass `{ssr:false}` to next/dynamic, so we
// wrap the import in this client component and let panel + admin
// layouts statically import the shim.
"use client";

import dynamic from "next/dynamic";

const CommandPalette = dynamic(
  () =>
    import("@/components/panel/CommandPalette").then((m) => ({
      default: m.CommandPalette,
    })),
  { ssr: false },
);

export default function CommandPaletteLazy() {
  return <CommandPalette />;
}
