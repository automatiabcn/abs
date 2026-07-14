"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import { useEffect, useState } from "react";

// "A new version is out" was the one thing the retired vanilla panel showed that
// this one did not. An operator who never learns a release shipped is an operator
// running a version with a known bug in it, so the notice belongs on the surface
// they actually open.
//
// GET /v1/update/check is public; POST /v1/update/apply needs the admin cookie,
// and apply only *requests* the pull — the host still runs docker compose. The
// banner says so rather than implying the update installs itself.

interface UpdateState {
  state: "current" | "available" | "critical" | "unknown";
  current: string;
  latest?: string;
  changelog_url?: string | null;
  changelog_summary?: string | null;
  critical?: boolean;
  breaking?: boolean;
}

type ApplyState = "idle" | "requesting" | "requested" | "failed";

const DISMISS_KEY = "abs-update-banner-dismissed";

export default function UpdateBanner() {
  const [update, setUpdate] = useState<UpdateState | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [apply, setApply] = useState<ApplyState>("idle");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/v1/update/check", { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) setUpdate(data as UpdateState);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  if (!update || dismissed) return null;
  // `unknown` means we could not reach the registry. That is not news to an
  // operator and it is not an update, so it stays silent.
  if (update.state !== "available" && update.state !== "critical") return null;

  // A dismissed *critical* update comes back on the next load: the dismissal is
  // remembered per version, so it cannot outlive the release it was about.
  const key = `${DISMISS_KEY}:${update.latest ?? ""}`;
  if (typeof window !== "undefined" && window.sessionStorage.getItem(key) === "1") {
    return null;
  }

  const critical = update.state === "critical" || update.critical === true;
  const tone = critical ? "var(--abs-danger)" : "var(--abs-info)";
  const toneSoft = critical ? "var(--abs-danger-soft)" : "var(--abs-info-soft)";

  async function requestUpdate() {
    setApply("requesting");
    try {
      const response = await fetch("/v1/update/apply", {
        method: "POST",
        credentials: "include",
      });
      setApply(response.ok ? "requested" : "failed");
    } catch {
      setApply("failed");
    }
  }

  return (
    <div
      data-testid="update-banner"
      role="region"
      aria-label={critical ? "Critical update available" : "Update available"}
      style={{
        position: "sticky",
        top: 0,
        zIndex: 49,
        background: toneSoft,
        color: tone,
        borderBottom: `1px solid ${tone}`,
        padding: "7px 16px",
        fontSize: 13,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        flexWrap: "wrap",
      }}
    >
      <span>
        <strong>
          {critical ? "Critical update" : "New version"} {update.latest}
        </strong>{" "}
        — you are on {update.current}
        {update.breaking ? ", and it contains breaking changes" : ""}.
        {update.changelog_summary ? ` ${update.changelog_summary}` : ""}
      </span>

      {update.changelog_url ? (
        <a
          href={update.changelog_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="update-banner-changelog"
          style={{ color: tone, textDecoration: "underline" }}
        >
          What changed
        </a>
      ) : null}

      {apply === "requested" ? (
        <span data-testid="update-banner-requested">
          Requested. Run <code>docker compose pull &amp;&amp; docker compose up -d</code> on
          the host to finish.
        </span>
      ) : (
        <button
          type="button"
          data-testid="update-banner-apply"
          onClick={requestUpdate}
          disabled={apply === "requesting"}
          style={{
            background: tone,
            border: `1px solid ${tone}`,
            color: "var(--abs-fg-inverted)",
            borderRadius: "var(--abs-radius-sm)",
            padding: "1px 8px",
            cursor: apply === "requesting" ? "default" : "pointer",
            fontSize: 12,
          }}
        >
          {apply === "requesting" ? "Requesting…" : "Pull this version"}
        </button>
      )}

      {apply === "failed" ? (
        <span data-testid="update-banner-error">
          Could not request the update — sign in as an admin and try again.
        </span>
      ) : null}

      <button
        type="button"
        data-testid="update-banner-dismiss"
        onClick={() => {
          window.sessionStorage.setItem(key, "1");
          setDismissed(true);
        }}
        style={{
          background: "transparent",
          border: `1px solid ${tone}`,
          color: tone,
          borderRadius: "var(--abs-radius-sm)",
          padding: "1px 8px",
          cursor: "pointer",
          fontSize: 12,
        }}
        aria-label="Dismiss update notice"
      >
        Dismiss
      </button>
    </div>
  );
}
