// The update feed answers the URL shape the shipped editor asks for, in the
// shape it can act on — and never tells a current build to update forever.
//
// Audit 2026-08-18: the editor (VSCodium update patch) asks
// `{updateUrl}/stable/{platform}/{arch}/latest.json`; the app only had the
// upstream `/api/update/{platform}/{quality}/{commit}` route, and that one
// compared the editor's COMMIT with the artefact's sha256 — never equal.

import { describe, expect, it, vi, beforeEach } from "vitest";

const state: { RELEASE: unknown } = { RELEASE: null };
vi.mock("@/lib/downloads", () => ({
  get RELEASE() {
    return state.RELEASE;
  },
}));

const params = <T extends object>(p: T) => ({ params: Promise.resolve(p) });
const req = new Request("http://x/");

describe("/stable/{platform}/{arch}/latest.json (VSCodium shape)", () => {
  beforeEach(() => {
    state.RELEASE = null;
  });

  it("answers 204 while no editor build is published", async () => {
    const { GET } = await import("@/app/stable/[platform]/[arch]/latest.json/route");
    const res = await GET(req, params({ platform: "darwin", arch: "arm64" }));
    expect(res.status).toBe(204);
  });

  it("describes the build in the fields the editor compares and downloads", async () => {
    state.RELEASE = {
      version: "1.1.0",
      published: "2026-09-01",
      editor: [
        {
          platform: "macos",
          label: "macOS",
          href: "https://dl.example/1.1.0/ABS.zip",
          sha256: "abc",
          productVersion: "1.126.04524-abs.3",
          commit: "deadbeef",
        },
      ],
      server: { platform: "linux", label: "s", href: "https://dl.example/s.tgz" },
    };
    const { GET } = await import("@/app/stable/[platform]/[arch]/latest.json/route");
    const res = await GET(req, params({ platform: "darwin", arch: "arm64" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.url).toBe("https://dl.example/1.1.0/ABS.zip");
    expect(body.version).toBe("deadbeef");
    expect(body.productVersion).toBe("1.126.04524-abs.3");
    expect(body.sha256hash).toBe("abc");
  });

  it("a build without productVersion/commit is not offered (the editor could not compare it)", async () => {
    state.RELEASE = {
      version: "1.1.0",
      published: "2026-09-01",
      editor: [{ platform: "macos", label: "m", href: "https://dl.example/x" }],
      server: { platform: "linux", label: "s", href: "https://dl.example/s.tgz" },
    };
    const { GET } = await import("@/app/stable/[platform]/[arch]/latest.json/route");
    const res = await GET(req, params({ platform: "darwin", arch: "arm64" }));
    expect(res.status).toBe(204);
  });

  it("an unknown platform is 204, not an error", async () => {
    const { GET } = await import("@/app/stable/[platform]/[arch]/latest.json/route");
    const res = await GET(req, params({ platform: "plan9", arch: "mips" }));
    expect(res.status).toBe(204);
  });
});

describe("/api/update/{platform}/{quality}/{commit} (upstream shape)", () => {
  beforeEach(() => {
    state.RELEASE = {
      version: "1.1.0",
      published: "2026-09-01",
      editor: [
        {
          platform: "macos",
          label: "macOS",
          href: "https://dl.example/1.1.0/ABS.zip",
          sha256: "abc",
          productVersion: "1.126.04524-abs.3",
          commit: "deadbeef",
        },
      ],
      server: { platform: "linux", label: "s", href: "https://dl.example/s.tgz" },
    };
  });

  it("a build asking with the published commit is current (204)", async () => {
    const { GET } = await import("@/app/api/update/[platform]/[quality]/[commit]/route");
    const res = await GET(req, params({ platform: "darwin-arm64", quality: "stable", commit: "deadbeef" }));
    expect(res.status).toBe(204);
  });

  it("another commit is offered the build, keyed by commit not by file hash", async () => {
    const { GET } = await import("@/app/api/update/[platform]/[quality]/[commit]/route");
    const res = await GET(req, params({ platform: "darwin-arm64", quality: "stable", commit: "0ld" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.version).toBe("deadbeef");
    expect(body.productVersion).toBe("1.126.04524-abs.3");
  });
});
