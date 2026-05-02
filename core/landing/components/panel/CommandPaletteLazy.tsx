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
