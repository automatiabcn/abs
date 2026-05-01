// Q8 Phase C — `/panel/tools` MCP tool browser. Renders 122-tool inventory
// from `/v1/panel/tools` as a TanStack Table with category sidebar +
// fuzzy search + slide-in detail Sheet (input schema + Try-it cascade run).
"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpDown,
  Layers,
  Search,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface ToolParam {
  name: string;
  type: string;
}

interface ToolItem {
  name: string;
  description: string;
  category: string;
  input_schema: { required: string[]; properties: ToolParam[] };
}

interface ToolsResponse {
  total: number;
  filtered_count: number;
  category_counts: Record<string, number>;
  tools: ToolItem[];
}

const CATEGORY_TONE: Record<string, string> = {
  provider: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  quality: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  judge: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  rag: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  workflow: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  fullstack: "bg-pink-500/15 text-pink-300 border-pink-500/30",
  research: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  system: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  admin: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  vault: "bg-orange-500/15 text-orange-300 border-orange-500/30",
};

function CategoryBadge({ category }: { category: string }) {
  const tone =
    CATEGORY_TONE[category] ?? "bg-muted text-muted-foreground border-border";
  return (
    <span
      data-test="category-badge"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        tone,
      )}
    >
      <Layers className="h-2.5 w-2.5" />
      {category}
    </span>
  );
}

async function fetchTools(): Promise<ToolsResponse> {
  const res = await fetch("/v1/panel/tools", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

interface TryItResult {
  status: "idle" | "running" | "ok" | "error";
  detail?: string;
  output?: string;
}

function ToolDetailSheet({
  tool,
  open,
  onClose,
}: {
  tool: ToolItem | null;
  open: boolean;
  onClose: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<TryItResult>({ status: "idle" });

  async function tryIt() {
    if (!prompt.trim() || !tool) return;
    setResult({ status: "running" });
    try {
      const res = await fetch("/v1/cascade/run", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: `${tool.name}: ${prompt}`, max_tokens: 256 }),
      });
      if (!res.ok) {
        const text = await res.text();
        setResult({ status: "error", detail: `HTTP ${res.status}`, output: text.slice(0, 800) });
        return;
      }
      const data = await res.json();
      setResult({
        status: "ok",
        detail: data.provider,
        output: data.completion ?? JSON.stringify(data, null, 2),
      });
    } catch (exc) {
      setResult({
        status: "error",
        detail: exc instanceof Error ? exc.message : "unknown",
      });
    }
  }

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-xl"
        data-test="tool-detail-sheet"
      >
        {tool && (
          <>
            <SheetHeader>
              <div className="mb-2 flex items-center gap-2">
                <CategoryBadge category={tool.category} />
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                  {tool.name}
                </code>
              </div>
              <SheetTitle className="font-mono text-base">
                {tool.name}
              </SheetTitle>
              <SheetDescription>{tool.description || "—"}</SheetDescription>
            </SheetHeader>

            <section className="mt-6">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Girdi şeması
              </h4>
              {tool.input_schema.properties.length === 0 ? (
                <p className="text-sm text-muted-foreground">Parametre yok.</p>
              ) : (
                <div className="rounded-md border border-border bg-card/40">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 text-left">İsim</th>
                        <th className="px-3 py-2 text-left">Tür</th>
                        <th className="px-3 py-2 text-left">Zorunlu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tool.input_schema.properties.map((p) => (
                        <tr key={p.name} className="border-t border-border">
                          <td className="px-3 py-2 font-mono">{p.name}</td>
                          <td className="px-3 py-2 text-muted-foreground">{p.type}</td>
                          <td className="px-3 py-2">
                            {tool.input_schema.required.includes(p.name) ? (
                              <Badge variant="outline" className="text-[10px]">
                                gerekli
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">opsiyonel</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="mt-6">
              <h4 className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <span>Dene</span>
                <Badge variant="outline" className="text-[10px]">
                  cascade router
                </Badge>
              </h4>
              <textarea
                rows={3}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={`${tool.name} aracını test etmek için bir prompt yazın`}
                className="w-full rounded-md border border-border bg-background p-2 text-sm outline-none focus:border-primary/50"
                data-test="tool-tryit-input"
              />
              <Button
                type="button"
                onClick={tryIt}
                disabled={result.status === "running" || !prompt.trim()}
                className="mt-2 w-full"
                data-test="tool-tryit-run"
              >
                {result.status === "running" ? "Çalıştırılıyor…" : "Çalıştır"}
              </Button>
              {result.status !== "idle" && (
                <div
                  data-test="tool-tryit-result"
                  className={cn(
                    "mt-3 rounded-md border p-3 text-sm",
                    result.status === "ok"
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
                      : result.status === "error"
                        ? "border-rose-500/30 bg-rose-500/10 text-rose-100"
                        : "border-border bg-muted/40",
                  )}
                >
                  <div className="mb-1 text-[11px] uppercase tracking-wider opacity-70">
                    {result.status} {result.detail ? `· ${result.detail}` : ""}
                  </div>
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs">
                    {result.output ?? "—"}
                  </pre>
                </div>
              )}
            </section>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function ToolsPage() {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "category", desc: false },
  ]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 });
  const [openTool, setOpenTool] = useState<ToolItem | null>(null);

  const tools = useQuery<ToolsResponse>({
    queryKey: ["panel", "tools"],
    queryFn: fetchTools,
  });

  const allTools = tools.data?.tools ?? [];
  const categoryCounts = tools.data?.category_counts ?? {};

  const filtered = useMemo(() => {
    let list = allTools;
    if (activeCategory) list = list.filter((t) => t.category === activeCategory);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q),
      );
    }
    return list;
  }, [allTools, activeCategory, search]);

  const columns = useMemo<ColumnDef<ToolItem>[]>(
    () => [
      {
        accessorKey: "name",
        header: ({ column }) => (
          <button
            type="button"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
          >
            Tool <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => (
          <code className="font-mono text-xs text-foreground">
            {row.original.name}
          </code>
        ),
      },
      {
        accessorKey: "category",
        header: "Kategori",
        cell: ({ row }) => <CategoryBadge category={row.original.category} />,
      },
      {
        accessorKey: "description",
        header: "Açıklama",
        cell: ({ row }) => (
          <span className="line-clamp-2 text-xs text-muted-foreground">
            {row.original.description || "—"}
          </span>
        ),
      },
      {
        id: "params",
        header: "Param",
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">
            {row.original.input_schema.properties.length}
          </span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const sortedCategories = useMemo(
    () =>
      Object.entries(categoryCounts)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
    [categoryCounts],
  );

  return (
    <main
      data-page="panel-tools"
      className="mx-auto flex h-[calc(100vh-3.5rem)] w-full max-w-7xl gap-6 px-6 py-6"
    >
      {/* ─── Category sidebar ──────────────────────────── */}
      <aside
        data-test="tools-category-sidebar"
        className="hidden w-56 shrink-0 flex-col gap-1 lg:flex"
      >
        <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Kategoriler
        </div>
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={cn(
            "flex items-center justify-between rounded-md px-3 py-2 text-sm",
            activeCategory === null
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          <span>Tümü</span>
          <span className="text-xs">{tools.data?.total ?? 0}</span>
        </button>
        <div className="-mx-1 flex-1 overflow-y-auto px-1">
          {tools.isLoading ? (
            <div className="space-y-2 px-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-7 w-full" />
              ))}
            </div>
          ) : (
            sortedCategories.map(([cat, n]) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                data-test="category-filter"
                data-category={cat}
                className={cn(
                  "flex w-full items-center justify-between rounded-md px-3 py-1.5 text-sm transition-colors",
                  activeCategory === cat
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <span className="truncate">{cat}</span>
                <span className="text-xs">{n}</span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* ─── Main panel ────────────────────────────────── */}
      <section className="flex min-w-0 flex-1 flex-col">
        <motion.header
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="mb-4"
        >
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Wrench className="h-5 w-5 text-primary" />
            MCP Tool Browser
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            ABS Server üzerinde kayıtlı{" "}
            <strong className="text-foreground">
              {tools.data?.total ?? "…"}
            </strong>{" "}
            MCP tool. Sol panelden kategoriye filtreleyin, satıra tıklayarak
            detayı görün.
          </p>
        </motion.header>

        <div className="mb-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Araç adı veya açıklamasında ara…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
              data-test="tools-search"
            />
          </div>
          <span
            className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
            data-test="tools-result-count"
          >
            {filtered.length} sonuç
          </span>
        </div>

        <div className="flex-1 overflow-hidden rounded-md border border-border bg-card/40">
          <div className="h-full overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-card/90 backdrop-blur">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th
                        key={h.id}
                        className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {tools.isLoading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i} className="border-t border-border">
                      {Array.from({ length: 4 }).map((_, j) => (
                        <td key={j} className="px-3 py-2">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-3 py-12 text-center text-sm text-muted-foreground"
                    >
                      Eşleşen araç bulunamadı.
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      data-test="tools-row"
                      onClick={() => setOpenTool(row.original)}
                      className="cursor-pointer border-t border-border transition-colors hover:bg-accent/50"
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-3 py-2">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <div>
            Sayfa {table.getState().pagination.pageIndex + 1}/
            {table.getPageCount() || 1}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ArrowLeft className="h-3 w-3" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ArrowRight className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </section>

      <ToolDetailSheet
        tool={openTool}
        open={openTool !== null}
        onClose={() => setOpenTool(null)}
      />
    </main>
  );
}
