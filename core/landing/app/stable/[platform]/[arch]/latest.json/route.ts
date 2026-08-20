/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The update feed the shipped editor actually calls.
//
// Our build carries VSCodium's update patch, so it asks
// `{updateUrl}/{quality}/{platform}/{arch}/latest.json` — not the upstream
// `/api/update/{platform}/{quality}/{commit}` route this app had (audit
// 2026-08-18: the live editor logged a 404 against this path every hour). The
// reply is VSCodium's shape: `productVersion` is compared by semver against
// the running editor's own version; `version` is the build commit; `url` is
// what to download. No body / 204 means "you are current" — which is the true
// answer until RELEASE names an editor build for this platform.

import { NextResponse } from "next/server";

import { RELEASE, type Platform } from "@/lib/downloads";

const PLATFORMS: Record<string, Platform> = {
  darwin: "macos",
  win32: "windows",
  linux: "linux",
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ platform: string; arch: string }> },
) {
  const { platform } = await context.params;
  const ours = PLATFORMS[platform];
  if (!ours || !RELEASE) {
    return new NextResponse(null, { status: 204 });
  }
  const build = RELEASE.editor.find((b) => b.platform === ours);
  if (!build || !build.productVersion || !build.commit) {
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
