// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
//
// What /download promises has to be true.
//
// Two things went wrong here on 2026-08-03, both visible only by looking at the
// live page:
//
//   - The server archive is 18 KB and the size renderer rounded everything to
//     megabytes, so it printed "0 MB" beside the download link. The function's
//     own comment said a size of zero "reads as a broken file" — the guard it
//     described covered a *missing* size and did nothing for a real one that
//     happened to be small.
//   - `DOWNLOAD_HOST` named a subdomain with no DNS record. A page of links
//     that resolve to nothing looks exactly like a page of links that work.
//
// The pattern: the release data is a handful of literals that nothing checked,
// on the page where a customer either gets the product or does not.

import { describe, expect, it } from "vitest";
import { DOWNLOAD_HOST, RELEASE, assetUrl, fileSize } from "../lib/downloads";

describe("file sizes", () => {
  it("never says zero for a file that exists", () => {
    // The exact regression: the shipped archive.
    expect(fileSize(18788)).not.toMatch(/^0\s/);
    for (const bytes of [1, 999, 18788, 1024 * 1024 - 1]) {
      expect(fileSize(bytes), `${bytes} bytes`).not.toMatch(/^0\s/);
    }
  });

  it("uses a unit that suits the size", () => {
    expect(fileSize(512)).toBe("512 B");
    expect(fileSize(18788)).toBe("18 KB");
    expect(fileSize(150 * 1024 * 1024)).toBe("150 MB");
    expect(fileSize(2 * 1024 * 1024 * 1024)).toBe("2.0 GB");
  });

  it("says nothing when the size is unknown", () => {
    // Distinct from small: we would rather show no size than invent one.
    for (const bad of [undefined, 0, -1, NaN, Infinity]) {
      expect(fileSize(bad as number | undefined)).toBe("");
    }
  });
});

describe("the download host", () => {
  it("is a name that resolves today, not one we intend to use", () => {
    // `dl.automatiabcn.com` has no A record. Whatever host is configured here
    // must be one that answers now; this catches the aspirational value coming
    // back on a later edit.
    expect(DOWNLOAD_HOST).not.toContain("dl.automatiabcn.com");
    expect(DOWNLOAD_HOST).toMatch(/^https:\/\//);
  });

  it("builds asset URLs from the one host", () => {
    expect(assetUrl("1.0.4", "abs-server-1.0.4.tar.gz")).toBe(
      `${DOWNLOAD_HOST}/1.0.4/abs-server-1.0.4.tar.gz`,
    );
  });
});

describe("the published release", () => {
  it("either says nothing or says something checkable", () => {
    if (RELEASE === null) return; // "not published yet" is a valid state
    expect(RELEASE.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(RELEASE.published).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("the server link goes to the configured host and matches the version", () => {
    if (RELEASE === null) return;
    expect(RELEASE.server.href.startsWith(DOWNLOAD_HOST)).toBe(true);
    // A link left pointing at the previous release is the failure that looks
    // like success: the page says 1.0.4 and hands over 1.0.3.
    expect(RELEASE.server.href).toContain(RELEASE.version);
    expect(RELEASE.server.label).toContain(RELEASE.version);
  });

  it("publishes a checksum, so a careful customer can verify the file", () => {
    if (RELEASE === null) return;
    expect(RELEASE.server.sha256, "no checksum for the server archive").toMatch(
      /^[a-f0-9]{64}$/,
    );
  });

  it("shows a real size for the server archive", () => {
    if (RELEASE === null) return;
    expect(fileSize(RELEASE.server.size)).not.toBe("");
    expect(fileSize(RELEASE.server.size)).not.toMatch(/^0\s/);
  });
});
