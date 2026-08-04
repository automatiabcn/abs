/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The editor's update check.
//
// A VS Code fork asks `{updateUrl}/api/update/{platform}/{quality}/{commit}`
// and expects either 204 — you are current — or a JSON body describing the
// build to fetch. The fork shipped with `updateUrl` pointing at
// update.automatiabcn.com, which has no DNS record, alongside a downloadUrl on
// a GitHub repository that does not exist and release notes on
// abs.automatiabcn.com, the host swept out of everything else on 2026-08-03.
// It survived here because that sweep read emails, the landing app and the
// READMEs, and this file is in the editor.
//
// Moving `updateUrl` to a domain that resolves is only half a repair: a live
// host with no such route is worse than a dead one, because it looks
// configured. So the route exists, and it answers honestly.
//
// It answers 204 today. Auto-update on macOS goes through Squirrel, which
// checks the signature of what it downloads, and the builds are ad-hoc signed
// — an update it cannot verify is an update it will refuse, and telling the
// editor to fetch one would produce a failure the customer cannot act on. The
// editor also ships with `updateMode: "none"`, so nothing calls this yet. When
// there are signed builds, RELEASE gains an editor entry and this starts
// answering with it; until then "you are current" is the true answer, and the
// download page is where a new version is announced.

import { NextResponse } from "next/server";

import { RELEASE, type Platform } from "@/lib/downloads";

/** VS Code's platform strings, mapped to ours. Anything else is not ours. */
const PLATFORMS: Record<string, Platform> = {
  "darwin-arm64": "macos",
  "darwin-x64": "macos",
  darwin: "macos",
  "win32-x64": "windows",
  "win32-arm64": "windows",
  "linux-x64": "linux",
  "linux-arm64": "linux",
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ platform: string; quality: string; commit: string }> },
) {
  const { platform, commit } = await context.params;

  const ours = PLATFORMS[platform];
  if (!ours) {
    // Not a platform we build for. 204 rather than 404: the editor treats a
    // 404 as an error worth showing, and "no update for you" is not an error.
    return new NextResponse(null, { status: 204 });
  }

  const build = RELEASE?.editor.find((b) => b.platform === ours);
  if (!build || !RELEASE) {
    return new NextResponse(null, { status: 204 });
  }

  // The running build asks with its own commit. Same commit, nothing to do.
  if (commit && build.sha256 && commit === build.sha256) {
    return new NextResponse(null, { status: 204 });
  }

  return NextResponse.json({
    url: build.href,
    name: RELEASE.version,
    version: build.sha256 ?? RELEASE.version,
    productVersion: RELEASE.version,
    timestamp: Date.parse(RELEASE.published) || Date.now(),
    sha256hash: build.sha256 ?? "",
  });
}
