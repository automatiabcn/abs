"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import { useEffect, useId, useMemo, useState } from "react";
import {
  Cpu,
  GlobeHemisphereWest,
  LockKey,
  MagnifyingGlass,
  Memory,
  WarningCircle,
} from "@phosphor-icons/react";

import {
  PLUGIN_TYPE_LABEL,
  PLUGIN_TYPE_ORDER,
  type PluginManifest,
  type PluginType,
} from "@/lib/marketplace";

type FilterValue = PluginType | "all";

type MarketplacePanelProps = {
  initialPlugins: PluginManifest[];
  isAdmin: boolean;
  onInstall?: (m: PluginManifest) => void;
};

interface InstalledRow {
  plugin_id: string;
  version?: string;
  installed_at?: number | null;
}

interface InstalledResponse {
  tenant: string;
  installed: InstalledRow[];
}

async function fetchInstalled(): Promise<Set<string>> {
  try {
    const res = await fetch("/v1/marketplace/installed", {
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) return new Set();
    const data = (await res.json()) as InstalledResponse;
    return new Set((data.installed ?? []).map((r) => r.plugin_id));
  } catch {
    return new Set();
  }
}

export default function MarketplacePanel({
  initialPlugins,
  isAdmin,
  onInstall,
}: MarketplacePanelProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterValue>("all");
  const [selected, setSelected] = useState<PluginManifest | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  // Installed plugin ids drive the "Installed" badge +
  // "Remove" button. Refetched after every install/uninstall.
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const searchId = useId();

  useEffect(() => {
    let active = true;
    void fetchInstalled().then((s) => {
      if (active) setInstalledIds(s);
    });
    return () => {
      active = false;
    };
  }, []);

  // reset acknowledgement whenever the modal target changes.
  useEffect(() => {
    setAcknowledged(false);
  }, [selected?.id]);

  const filtered = useMemo(() => {
    let list = initialPlugins;
    if (filter !== "all") {
      list = list.filter((p) => p.type === filter);
    }
    const term = search.trim().toLowerCase();
    if (term) {
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(term) ||
          p.id.toLowerCase().includes(term) ||
          p.description.toLowerCase().includes(term),
      );
    }
    return list;
  }, [initialPlugins, filter, search]);

  useEffect(() => {
    if (!selected) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selected]);

  const handleApprove = async () => {
    if (!selected) return;
    if (onInstall) {
      onInstall(selected);
      setSelected(null);
      return;
    }
    setBusyId(selected.id);
    try {
      const res = await fetch("/v1/marketplace/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ plugin_id: selected.id, tenant: "default" }),
      });
      if (!res.ok && typeof console !== "undefined") {
        console.warn("install_failed", selected.id, res.status);
      }
      // Refresh installed list so the card flips to
      // "Installed" without forcing the operator to reload the page.
      const fresh = await fetchInstalled();
      setInstalledIds(fresh);
    } catch (exc) {
      if (typeof console !== "undefined") {
        console.warn("install_error", selected.id, exc);
      }
    } finally {
      setSelected(null);
      setBusyId(null);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    setBusyId(pluginId);
    try {
      const res = await fetch(
        `/v1/marketplace/uninstall/${encodeURIComponent(pluginId)}?tenant=default`,
        {
          method: "DELETE",
          credentials: "include",
        },
      );
      if (!res.ok && typeof console !== "undefined") {
        console.warn("uninstall_failed", pluginId, res.status);
      }
      const fresh = await fetchInstalled();
      setInstalledIds(fresh);
    } catch (exc) {
      if (typeof console !== "undefined") {
        console.warn("uninstall_error", pluginId, exc);
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-6">
      {!isAdmin && (
        <div
          data-testid="admin-banner"
          className="rounded-2xl bg-yellow-100 p-3 text-sm text-yellow-900 ring-1 ring-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-200 dark:ring-yellow-800"
        >
          Read-only — you need an admin role to install plugins
        </div>
      )}

      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="relative max-w-md flex-1">
          <MagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <label htmlFor={searchId} className="sr-only">
            Search plugins
          </label>
          <input
            id={searchId}
            data-testid="marketplace-search"
            aria-label="Search plugins"
            type="search"
            placeholder="Search plugins…"
            className="w-full rounded-xl border border-input bg-background py-2 pl-9 pr-3 text-sm text-foreground ring-1 ring-border focus:outline-none focus:ring-2 focus:ring-ring"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <FilterChip
            testId="filter-chip-all"
            active={filter === "all"}
            label="All"
            onClick={() => setFilter("all")}
          />
          {PLUGIN_TYPE_ORDER.map((t) => (
            <FilterChip
              key={t}
              testId={`filter-chip-${t}`}
              active={filter === t}
              label={PLUGIN_TYPE_LABEL[t]}
              onClick={() => setFilter(t)}
            />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((plugin) => (
          <article
            key={plugin.id}
            data-testid={`plugin-card-${plugin.id}`}
            className="flex flex-col rounded-2xl bg-muted/40 p-5 ring-1 ring-border"
          >
            <header>
              <h3 className="text-lg font-semibold text-foreground">
                {plugin.name}
              </h3>
              <div className="mt-1 flex items-center gap-2 text-xs">
                <span className="rounded-full bg-muted px-2 py-0.5 text-foreground">
                  {PLUGIN_TYPE_LABEL[plugin.type]}
                </span>
                <span className="font-mono text-muted-foreground">
                  v{plugin.version}
                </span>
                <span className="text-muted-foreground">
                  by {plugin.author}
                </span>
              </div>
            </header>
            <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">
              {plugin.description}
            </p>
            {/* permission preview chips on the card */}
            <div
              data-testid={`permission-preview-${plugin.id}`}
              className="mt-3 flex flex-wrap gap-1.5 text-[10px]"
            >
              {plugin.permissions.network_egress.length > 0 && (
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-800 ring-1 ring-blue-200 dark:bg-blue-900/30 dark:text-blue-200 dark:ring-blue-800">
                  network · {plugin.permissions.network_egress.length}
                </span>
              )}
              {plugin.permissions.secrets.length > 0 && (
                <span className="rounded-full bg-yellow-50 px-2 py-0.5 text-yellow-900 ring-1 ring-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-200 dark:ring-yellow-800">
                  secret · {plugin.permissions.secrets.length}
                </span>
              )}
              {plugin.permissions.filesystem_write.length > 0 && (
                <span className="rounded-full bg-orange-50 px-2 py-0.5 text-orange-900 ring-1 ring-orange-200 dark:bg-orange-900/30 dark:text-orange-200 dark:ring-orange-800">
                  fs-write · {plugin.permissions.filesystem_write.length}
                </span>
              )}
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-900 ring-1 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:ring-emerald-800">
                cosign · signed
              </span>
            </div>
            {installedIds.has(plugin.id) ? (
              <div
                className="mt-5 flex items-center gap-2"
                data-testid={`installed-row-${plugin.id}`}
              >
                <span
                  data-testid={`installed-badge-${plugin.id}`}
                  className="inline-flex items-center justify-center rounded-xl bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-900 ring-1 ring-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-200 dark:ring-emerald-800"
                >
                  Installed
                </span>
                <button
                  type="button"
                  data-testid={`uninstall-button-${plugin.id}`}
                  disabled={!isAdmin || busyId === plugin.id}
                  onClick={() => handleUninstall(plugin.id)}
                  className="ml-auto inline-flex items-center justify-center rounded-xl border border-rose-300 px-3 py-2 text-xs font-medium text-rose-700 transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-rose-50 dark:border-rose-700 dark:text-rose-200 dark:hover:enabled:bg-rose-900/20"
                >
                  {busyId === plugin.id ? "Removing…" : "Remove"}
                </button>
              </div>
            ) : (
              <button
                type="button"
                data-testid={`install-button-${plugin.id}`}
                disabled={!isAdmin || busyId === plugin.id}
                onClick={() => setSelected(plugin)}
                className="mt-5 inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-primary/90"
              >
                {busyId === plugin.id ? "Installing…" : "Install"}
              </button>
            )}
          </article>
        ))}
      </div>

      {selected && (
        <div
          data-testid="permission-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="permission-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="w-full max-w-lg rounded-2xl bg-card p-6 shadow-xl ring-1 ring-border">
            <h2
              id="permission-modal-title"
              className="text-xl font-semibold text-foreground"
            >
              Review permissions — {selected.name} v{selected.version}
            </h2>

            <dl className="mt-5 space-y-4 text-sm">
              <PermissionRow icon={<GlobeHemisphereWest className="size-4" />} label="Network egress">
                <ChipList items={selected.permissions.network_egress} />
              </PermissionRow>

              <PermissionRow icon={<WarningCircle className="size-4" />} label="Read-only mounts">
                <ChipList items={selected.permissions.filesystem_read} />
              </PermissionRow>

              <PermissionRow icon={<WarningCircle className="size-4" />} label="Writable (tmpfs)">
                <ChipList items={selected.permissions.filesystem_write} />
              </PermissionRow>

              <PermissionRow
                icon={<LockKey className="size-4" />}
                label={
                  selected.permissions.secrets.length > 0
                    ? "Secrets (sensitive)"
                    : "Secrets"
                }
              >
                {selected.permissions.secrets.length > 0 ? (
                  <ChipList items={selected.permissions.secrets} tone="warn" />
                ) : (
                  <span className="text-muted-foreground">None</span>
                )}
              </PermissionRow>

              <PermissionRow icon={<Cpu className="size-4" />} label="Resources">
                <span className="font-mono">
                  {selected.permissions.cpu_quota} cores ·{" "}
                  <Memory className="inline size-3.5 align-text-bottom" />{" "}
                  {selected.permissions.memory_mb} MB
                </span>
              </PermissionRow>

              <PermissionRow icon={<LockKey className="size-4" />} label="Scope">
                <span>{selected.permissions.tenant_scoped ? "Tenant-scoped" : "Global"}</span>
              </PermissionRow>
            </dl>

            {/* explicit warning + acknowledgement gate */}
            <div className="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200">
              This plugin will reach the network endpoints and read the
              secrets listed above. It runs in a sandbox, but once you approve,
              that access stays open until you remove the plugin.
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                data-testid="permission-acknowledge"
              />
              <span>I have read these permissions and approve the install.</span>
            </label>

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                data-testid="permission-cancel"
                onClick={() => setSelected(null)}
                className="rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="permission-approve"
                onClick={handleApprove}
                disabled={!acknowledged}
                className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Approve &amp; install
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function FilterChip({
  testId,
  label,
  active,
  onClick,
}: {
  testId: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      aria-pressed={active}
      className={
        "rounded-full px-3 py-1 text-xs font-medium ring-1 transition " +
        (active
          ? "bg-primary text-primary-foreground ring-primary"
          : "bg-background text-muted-foreground ring-border hover:bg-accent hover:text-foreground")
      }
    >
      {label}
    </button>
  );
}

function PermissionRow({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 text-muted-foreground">{icon}</div>
      <div className="flex-1">
        <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </dt>
        <dd className="mt-1">{children}</dd>
      </div>
    </div>
  );
}

function ChipList({ items, tone }: { items: string[]; tone?: "warn" }) {
  if (items.length === 0) {
    return <span className="text-muted-foreground">None</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className={
            "rounded-full px-2 py-0.5 text-xs ring-1 " +
            (tone === "warn"
              ? "bg-yellow-50 text-yellow-900 ring-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-200 dark:ring-yellow-800"
              : "bg-muted text-foreground ring-border")
          }
        >
          {item}
        </span>
      ))}
    </div>
  );
}
