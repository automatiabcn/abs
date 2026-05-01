"use client";

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

export default function MarketplacePanel({
  initialPlugins,
  isAdmin,
  onInstall,
}: MarketplacePanelProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterValue>("all");
  const [selected, setSelected] = useState<PluginManifest | null>(null);
  const searchId = useId();

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
    // P1 / S19-close — fall through to /api/marketplace/install proxy.
    try {
      const res = await fetch("/api/marketplace/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ plugin_id: selected.id, tenant: "default" }),
      });
      if (!res.ok && typeof console !== "undefined") {
        console.warn("install_failed", selected.id, res.status);
      }
    } catch (exc) {
      if (typeof console !== "undefined") {
        console.warn("install_error", selected.id, exc);
      }
    } finally {
      setSelected(null);
    }
  };

  return (
    <section className="space-y-6">
      {!isAdmin && (
        <div
          data-testid="admin-banner"
          className="rounded-2xl bg-yellow-100 p-3 text-sm text-yellow-900 ring-1 ring-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-200 dark:ring-yellow-800"
        >
          Read-only — admin role required to install plugins
        </div>
      )}

      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="relative max-w-md flex-1">
          <MagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" />
          <label htmlFor={searchId} className="sr-only">
            Search plugins
          </label>
          <input
            id={searchId}
            data-testid="marketplace-search"
            aria-label="Search plugins"
            type="search"
            placeholder="Search plugins…"
            className="w-full rounded-xl border border-zinc-200 bg-white py-2 pl-9 pr-3 text-sm text-zinc-900 ring-1 ring-zinc-900/5 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50"
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
            className="flex flex-col rounded-2xl bg-zinc-50 p-5 ring-1 ring-zinc-900/5 dark:bg-zinc-950 dark:ring-zinc-50/10"
          >
            <header>
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {plugin.name}
              </h3>
              <div className="mt-1 flex items-center gap-2 text-xs">
                <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                  {PLUGIN_TYPE_LABEL[plugin.type]}
                </span>
                <span className="font-mono text-zinc-500 dark:text-zinc-400">
                  v{plugin.version}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  by {plugin.author}
                </span>
              </div>
            </header>
            <p className="mt-3 line-clamp-3 text-sm text-zinc-600 dark:text-zinc-300">
              {plugin.description}
            </p>
            <button
              type="button"
              data-testid={`install-button-${plugin.id}`}
              disabled={!isAdmin}
              onClick={() => setSelected(plugin)}
              className="mt-5 inline-flex items-center justify-center rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:enabled:bg-zinc-200"
            >
              Install
            </button>
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
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl ring-1 ring-zinc-900/10 dark:bg-zinc-900 dark:ring-zinc-50/10">
            <h2
              id="permission-modal-title"
              className="text-xl font-semibold text-zinc-900 dark:text-zinc-50"
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
                  <span className="text-zinc-500">None</span>
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

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                data-testid="permission-cancel"
                onClick={() => setSelected(null)}
                className="rounded-xl border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="permission-approve"
                onClick={handleApprove}
                className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                Approve &amp; Install
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
          ? "bg-zinc-900 text-white ring-zinc-900 dark:bg-zinc-50 dark:text-zinc-900 dark:ring-zinc-50"
          : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-200 dark:ring-zinc-800 dark:hover:bg-zinc-800")
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
      <div className="mt-0.5 text-zinc-500">{icon}</div>
      <div className="flex-1">
        <dt className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {label}
        </dt>
        <dd className="mt-1">{children}</dd>
      </div>
    </div>
  );
}

function ChipList({ items, tone }: { items: string[]; tone?: "warn" }) {
  if (items.length === 0) {
    return <span className="text-zinc-500">None</span>;
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
              : "bg-zinc-100 text-zinc-800 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:ring-zinc-700")
          }
        >
          {item}
        </span>
      ))}
    </div>
  );
}
