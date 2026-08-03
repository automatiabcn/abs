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
 *
 * The `dl.` name has no A record yet — that is a founder task, and until it
 * lands the same Caddy site answers on its nip.io alias, which resolves from
 * the host's own IP and carries a real certificate. Using the name that works
 * today beats using the name we intend to use and shipping a page of dead
 * links; when the record exists, this one line changes.
 */
export const DOWNLOAD_HOST = "https://dl.168-119-104-24.nip.io";

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

/** The published release, or null when there is not one yet.
 *
 * `editor` is empty on purpose. The server archive is finished — built,
 * installed from scratch on 2026-08-03, and served from the download host with
 * a checksum that matches the file on this machine byte for byte. The editor
 * builds are not: the macOS one is unsigned, and handing someone a binary
 * Gatekeeper refuses to open is worse than telling them to wait.
 *
 * Half a release is still a release when the page says which half.
 */
export const RELEASE: Release | null = {
  version: "1.0.4",
  published: "2026-08-03",
  editor: [],
  server: {
    platform: "linux",
    label: "abs-server-1.0.4.tar.gz",
    href: assetUrl("1.0.4", "abs-server-1.0.4.tar.gz"),
    size: 18714,
    sha256: "a8ab8f50f495a232bae0489a100c9f2ff36f885ebac2742443b6248b40390185",
  },
};

export function platformLabel(p: Platform): string {
  return p === "macos" ? "macOS" : p === "windows" ? "Windows" : "Linux";
}

/** Human-readable size, or an empty string when we do not know it.
 *
 * Unknown is not zero: a build whose size we failed to record should show
 * nothing rather than "0 B", which reads as a broken file.
 *
 * Neither is small. This rounded everything to MB, so the 18 KB server archive
 * rendered as "0 MB" — seen on the live page on 2026-08-03, right next to the
 * download link, saying the file was empty. The guard above was written for a
 * missing size and did nothing for a real one that happened to be small. */
export function fileSize(bytes: number | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) {
    return "";
  }
  const kb = bytes / 1024;
  if (kb < 1) return `${Math.round(bytes)} B`;
  const mb = kb / 1024;
  if (mb < 1) return `${Math.round(kb)} KB`;
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}
