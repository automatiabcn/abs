/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Where ABS Studio is downloaded from.
//
// The source repository is private and stays private, so GitHub Releases is
// not the delivery surface — the builds are served from this domain. The
// licence email and the install guide both point here, which makes this file
// the single place a wrong URL can be wrong in.
//
// BUILDS is empty until a release is actually published. That is deliberate:
// an empty list renders as "not published yet" and a customer sees the truth,
// where a hard-coded button would render as a working download and 404.

/** Where the files themselves are served from.
 *
 * Not this domain: the landing is a Next.js app on a platform that bills
 * bandwidth and caps deployment size, which is the wrong shape for 150 MB
 * binaries. They sit on the Hetzner box behind the Caddy gateway that already
 * runs there — 20 TB/month of traffic that is already paid for, and TLS Caddy
 * obtains by itself.
 *
 * Verified end-to-end on 08-02: a 5 MB file fetched from outside came back
 * with a matching sha256 over a Let's Encrypt certificate.
 */
export const DOWNLOAD_HOST = "https://dl.automatiabcn.com";

/** The one function that builds a download URL, so a release never hand-writes
 * a host and gets it subtly wrong. */
export function assetUrl(version: string, filename: string): string {
  return `${DOWNLOAD_HOST}/${encodeURIComponent(version)}/${encodeURIComponent(filename)}`;
}

export type Platform = "macos" | "windows" | "linux";

export type Build = {
  platform: Platform;
  /** What a person calls it, e.g. "macOS (Apple silicon)". */
  label: string;
  /** Absolute path on this domain. Never a third-party host. */
  href: string;
  /** Bytes, for showing a size next to the link. */
  size?: number;
  /** Hex sha256 so a careful customer can verify what they downloaded. */
  sha256?: string;
};

export type Release = {
  version: string;
  /** ISO date. */
  published: string;
  /** The editor builds, one per platform. */
  editor: Build[];
  /** The server archive — versioned WITH the editor, never separately. */
  server: Build;
};

/** The published release, or null when there is not one yet. */
export const RELEASE: Release | null = null;

export function platformLabel(p: Platform): string {
  return p === "macos" ? "macOS" : p === "windows" ? "Windows" : "Linux";
}

/** Human-readable size, or an empty string when we do not know it.
 *
 * Unknown is not zero: a build whose size we failed to record should show
 * nothing rather than "0 B", which reads as a broken file. */
export function fileSize(bytes: number | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) {
    return "";
  }
  const mb = bytes / (1024 * 1024);
  return mb >= 1024
    ? `${(mb / 1024).toFixed(1)} GB`
    : `${Math.round(mb)} MB`;
}
