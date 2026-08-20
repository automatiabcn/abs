// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// Bring docs/CHANGELOG.md into the landing tree before the build.
//
// The changelog page read it from the repo root and rendered fine locally, then
// showed its "could not be read" fallback in production: the deployment uploads
// this directory, so a file two levels above it is simply not there. Caught by
// looking at the live page rather than by trusting a green build — the same
// gap that made a build-passes/production-fails class possible at all.
//
// Copied by a script rather than kept as a second file: a changelog maintained
// in two places is one that disagrees with itself, and the copy is regenerated
// on every build from the one release engineering already writes to.

import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "..", "docs", "CHANGELOG.md");
const target = join(here, "..", "content", "CHANGELOG.md");

try {
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
  console.log(`changelog: ${source} -> ${target}`);
} catch (err) {
  // A build must not fail over this — the page has an honest fallback — but it
  // must not pass silently either, or the fallback becomes permanent and
  // nobody notices the changelog stopped updating.
  console.warn(`changelog: could not copy from ${source}: ${err.message}`);
  process.exitCode = 0;
}
