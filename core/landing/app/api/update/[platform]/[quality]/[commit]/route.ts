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
// editor to fetch one would produce a failure the customer cannot act on.
//
// Note (2026-08-18): this is the shape Microsoft's VS Code asks for. OUR
// build carries VSCodium's update patch and asks
// `{updateUrl}/{quality}/{platform}/{arch}/latest.json` instead — see
// app/stable/[platform]/[arch]/latest.json/route.ts, which is the route the
// shipped editor actually calls. This one stays for tools that speak the
// upstream shape. The editor does NOT ship with updates disabled: it checks
// on start, and both routes answer 204 until RELEASE names an editor build.

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

  // The running build asks with its own COMMIT. This compared it with the
  // artefact's file hash — never equal — so once a release existed every
  // editor would have been told to update, forever (audit 2026-08-18).
  if (commit && build.commit && commit === build.commit) {
    return new NextResponse(null, { status: 204 });
  }
  if (!build.productVersion || !build.commit) {
    // Half-described build: better "you are current" than a feed entry the
    // editor cannot compare or verify.
    return new NextResponse(null, { status: 204 });
  }

  return NextResponse.json({
    url: build.href,
    name: RELEASE.version,
    version: build.commit,
    productVersion: build.productVersion,
    timestamp: Date.parse(RELEASE.published) || Date.now(),
    sha256hash: build.sha256 ?? "",
  });
}
