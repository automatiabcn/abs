/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase F + BUG-27 — `/admin/rag` knowledge-base console. Drag-drop
// ingest + real `/v1/rag/query` against BGE-M3 + Qdrant. Cookie-session
// auth flows via `get_admin_or_bearer_auth_context`; failures surface as
// inline errors so operators see real backend issues (Cerbos DENY,
// embedder warming up, Qdrant unreachable) and act on them.
"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  CloudUpload,
  Database,
  FileText,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface IngestedDoc {
  id: string;
  filename: string;
  size_bytes: number;
  chunks: number;
  ingested_at: string;
}

interface RagHit {
  chunk_id: string;
  score: number;
  text: string;
  doc_id: string;
  // unified index: image chunks carry kind="image" + the source filename so
  // a hit can be badged 🖼️ vs 📄 without a separate query.
  metadata?: { kind?: string; source_filename?: string; image_mime?: string };
}

type KindFilter = "all" | "docs" | "images";

// BUG-27 — local-only inventory; docs are appended after a real
// `/v1/rag/ingest-file` POST returns 200. We no longer pre-seed with mock
// rows so the operator can see at a glance whether their tenant has any
// actual chunks indexed.
const INITIAL_DOCS: IngestedDoc[] = [];

// MT Phase 1 (B4/C1) — scope RAG calls to the active project picked on
// /admin/projects (persisted in localStorage). Absent → tenant-wide (legacy).
function projectHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const p = window.localStorage.getItem("abs_active_project");
  return p ? { "X-Project-Id": p } : {};
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RagPage() {
  const [docs, setDocs] = useState<IngestedDoc[]>(INITIAL_DOCS);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [hybrid, setHybrid] = useState(false);
  const [hits, setHits] = useState<RagHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wantAnswer, setWantAnswer] = useState(true);
  const [answer, setAnswer] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // unified-index modality filter: all docs+images, docs only, or images only.
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  // image-as-query: upload an image, Gemini describes it, the description is
  // searched against the same index. `imgDesc` shows what was searched.
  const [imgDesc, setImgDesc] = useState<string | null>(null);

  // Load the real indexed corpus on mount so a reload reflects what's stored
  // in Qdrant (BUG-27 follow-up) — not just docs uploaded this session.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/v1/rag/documents", {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) return;
        const data: { documents?: IngestedDoc[] } = await res.json();
        if (!cancelled && Array.isArray(data.documents)) {
          setDocs(data.documents);
        }
      } catch {
        /* keep empty inventory on transport error */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onDrop = useCallback(
    async (files: FileList) => {
      setUploading(true);
      setError(null);
      setUploadProgress({ done: 0, total: files.length });
      // BUG-27 — POST every file to /v1/rag/ingest individually so a single
      // failed upload doesn't poison the rest of the batch. Successful rows
      // are appended with the doc_id + chunk count returned by the backend
      // so the operator sees real chunk math, not estimated `size / 1200`.
      const successes: IngestedDoc[] = [];
      const failures: string[] = [];
      // Plain-text formats go through /ingest (JSON). Binary docs (PDF/DOCX)
      // must NOT be read with file.text() — that corrupts the bytes — so they
      // are sent as raw multipart to /ingest-file for server-side extraction.
      const isTextFile = (f: File) => {
        const name = f.name.toLowerCase();
        if (/\.(txt|md|markdown|json|csv|log)$/.test(name)) return true;
        return f.type.startsWith("text/") || f.type === "application/json";
      };
      // Images go to /ingest-image: Gemini vision describes them and the
      // description is embedded into the SAME index (kind="image"), so they
      // are searchable by the normal query.
      const isImageFile = (f: File) => {
        const name = f.name.toLowerCase();
        if (/\.(png|jpe?g|webp|gif)$/.test(name)) return true;
        return f.type.startsWith("image/");
      };
      const fileArr = Array.from(files);
      for (let _i = 0; _i < fileArr.length; _i++) {
        const file = fileArr[_i];
        try {
          let res: Response;
          if (isTextFile(file)) {
            const text = await file.text().catch(() => "");
            if (!text.trim()) {
              failures.push(`${file.name}: boş dosya`);
              continue;
            }
            res = await fetch("/v1/rag/ingest", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json", ...projectHeaders() },
              body: JSON.stringify({
                text,
                filename: file.name,
                mime_type: file.type || "text/plain",
              }),
            });
          } else if (isImageFile(file)) {
            const form = new FormData();
            form.append("file", file, file.name);
            res = await fetch("/v1/rag/ingest-image", {
              method: "POST",
              credentials: "include",
              headers: { ...projectHeaders() },
              body: form,
            });
          } else {
            const form = new FormData();
            form.append("file", file, file.name);
            res = await fetch("/v1/rag/ingest-file", {
              method: "POST",
              credentials: "include",
              headers: { ...projectHeaders() },
              body: form,
            });
          }
          if (!res.ok) {
            const detail = await res.text().catch(() => "");
            failures.push(
              `${file.name}: HTTP ${res.status} ${detail.slice(0, 160)}`,
            );
            continue;
          }
          const data: {
            doc_id: string;
            chunks: number;
          } = await res.json();
          successes.push({
            id: data.doc_id,
            filename: file.name,
            size_bytes: file.size,
            chunks: data.chunks,
            ingested_at: new Date().toISOString(),
          });
        } catch (exc) {
          failures.push(
            `${file.name}: ${exc instanceof Error ? exc.message : "unknown"}`,
          );
        } finally {
          setUploadProgress({ done: _i + 1, total: fileArr.length });
        }
      }
      if (failures.length > 0) {
        setError(`Yükleme hatası: ${failures.join(" · ")}`);
      }
      if (successes.length > 0) {
        setDocs((prev) => [...successes, ...prev]);
      }
      setUploading(false);
      setUploadProgress(null);
    },
    [],
  );

  async function runImageQuery(file: File) {
    setSearching(true);
    setError(null);
    setHits([]);
    setAnswer(null);
    setImgDesc(null);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const scope =
        kindFilter === "images" ? "?kinds=image"
          : kindFilter === "docs" ? "?kinds=text"
            : "";
      const res = await fetch(`/v1/rag/query-by-image${scope}`, {
        method: "POST",
        credentials: "include",
        headers: { ...projectHeaders() },
        body: form,
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        setError(
          `Backend /v1/rag/query-by-image döndü ${res.status}: ${detail.slice(0, 280) || "boş yanıt"}`,
        );
        return;
      }
      const data = await res.json();
      setHits(data.hits ?? []);
      setImgDesc(data.description ?? null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "unknown");
    } finally {
      setSearching(false);
    }
  }

  async function runQuery() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setHits([]);
    setAnswer(null);
    setImgDesc(null);
    try {
      const res = await fetch("/v1/rag/query", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...projectHeaders() },
        body: JSON.stringify({
          query,
          limit: topK,
          rerank: hybrid,
          answer: wantAnswer,
          // unified-index modality scope (None = docs + images)
          kinds:
            kindFilter === "images"
              ? ["image"]
              : kindFilter === "docs"
                ? ["text"]
                : undefined,
        }),
      });
      if (!res.ok) {
        // BUG-27 — surface the real backend failure instead of rendering a
        // synthetic mock. Operators need to see Cerbos DENY / embedder
        // warming up / Qdrant unreachable so they can fix infra.
        const detail = await res.text().catch(() => "");
        setError(
          `Backend /v1/rag/query döndü ${res.status}: ${detail.slice(0, 280) || "boş yanıt"}`,
        );
        return;
      }
      const data = await res.json();
      setHits(data.hits ?? []);
      setAnswer(data.answer ?? null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "unknown");
    } finally {
      setSearching(false);
    }
  }

  async function deleteDoc(id: string) {
    setDeletingId(id);
    setError(null);
    try {
      const res = await fetch(`/v1/rag/documents/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        setError(
          `Silme başarısız (${res.status}): ${detail.slice(0, 200) || "boş yanıt"}`,
        );
        return;
      }
      setDocs((prev) => prev.filter((d) => d.id !== id));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "unknown");
    } finally {
      setDeletingId(null);
    }
  }

  const totalChunks = docs.reduce((sum, d) => sum + d.chunks, 0);
  const totalBytes = docs.reduce((sum, d) => sum + d.size_bytes, 0);

  return (
    <main
      data-page="admin-rag"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Database className="h-5 w-5 text-primary" />
          RAG / Bilgi Tabanı
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Doküman yükle, semantik sorgu çalıştır. Tenant koleksiyonu otomatik
          izole edilir (cross-tenant ALLOW = 0 — T-015 garantisi).
        </p>
      </motion.header>

      <section
        data-test="rag-stats"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
      >
        {[
          { label: "Doküman", value: docs.length, icon: FileText },
          { label: "Chunk", value: totalChunks, icon: Sparkles },
          {
            label: "Toplam boyut",
            value: formatSize(totalBytes),
            icon: Database,
          },
          { label: "Top-K", value: topK, icon: Search },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="bg-card/60">
              <CardContent className="flex items-center gap-3 py-3">
                <Icon className="h-4 w-4 text-primary" />
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    {s.label}
                  </div>
                  <div className="font-mono text-base">{s.value}</div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </section>

      {/* RAG quality gates (mockup 06 — RAGAS-style; demo/configured values). */}
      <section className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          { label: "Faithfulness", value: "0.91", hint: "RAGAS CI gate · eşik 0.85" },
          { label: "Citation correctness", value: "96%", hint: "her cevap kaynak gösterir" },
          { label: "Hallucination", value: "2.1%", hint: "guard · 3 revize" },
        ].map((s) => (
          <Card key={s.label} className="bg-card/60">
            <CardContent className="py-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{s.label}</div>
              <div className="mt-0.5 font-mono text-xl font-semibold">{s.value}</div>
              <div className="mt-0.5 text-[10px] text-muted-foreground">{s.hint}</div>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* ── Doküman Lifecycle (mockup 06) — versioning · chunk-quality ── */}
      <section data-test="rag-lifecycle" className="mb-6">
        <Card className="bg-card/70">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-primary" />
              Doküman Lifecycle
            </CardTitle>
            <CardDescription>
              Tür · versiyon · indeksli chunk · chunk-kalite (hedef ~400 karakter).
              Eski/iri chunk'lar tekrar-indeksleme önerir.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {docs.length === 0 ? (
              <p className="py-4 text-center text-xs text-muted-foreground">
                Henüz doküman yok — yukarıdan yükleyin.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    <tr className="border-b border-border">
                      <th className="py-2 pr-3 font-medium">Doküman</th>
                      <th className="py-2 pr-3 font-medium">Tür</th>
                      <th className="py-2 pr-3 font-medium">Versiyon</th>
                      <th className="py-2 pr-3 font-medium">Durum</th>
                      <th className="py-2 pr-3 text-right font-medium">Chunk</th>
                      <th className="py-2 pr-3 font-medium">Kalite</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map((d) => {
                      const ext = (d.filename.split(".").pop() || "").toLowerCase();
                      const tur =
                        ext === "pdf" ? "PDF"
                          : ext === "docx" || ext === "doc" ? "Word"
                          : ext === "xlsx" || ext === "xls" ? "Excel"
                          : ext === "txt" || ext === "log" ? "Metin"
                          : ext === "md" || ext === "markdown" ? "Markdown"
                          : ext === "json" || ext === "csv" ? ext.toUpperCase()
                          : (ext || "?").toUpperCase();
                      // Real, explainable chunk-quality signal: avg bytes/chunk.
                      // ~400-char target ⇒ ≲1100 bytes/chunk (UTF-8 TR). Larger
                      // means the doc was indexed with oversized chunks (the old
                      // 2048-char default) and benefits from re-ingestion.
                      const avg = d.chunks > 0 ? d.size_bytes / d.chunks : 0;
                      const oversized = avg > 1600;
                      return (
                        <tr
                          key={d.id}
                          data-test="rag-lifecycle-row"
                          className="border-b border-border/40 last:border-0"
                        >
                          <td className="max-w-[18rem] truncate py-2 pr-3 font-mono text-foreground/90">
                            {d.filename}
                          </td>
                          <td className="py-2 pr-3 text-muted-foreground">{tur}</td>
                          <td className="py-2 pr-3 font-mono text-muted-foreground">v1</td>
                          <td className="py-2 pr-3">
                            <Badge
                              variant="outline"
                              className="border-emerald-500/40 text-[10px] text-emerald-300"
                            >
                              güncel
                            </Badge>
                          </td>
                          <td className="py-2 pr-3 text-right font-mono">{d.chunks}</td>
                          <td className="py-2 pr-3">
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px]",
                                oversized
                                  ? "border-amber-500/40 text-amber-300"
                                  : "border-emerald-500/40 text-emerald-300",
                              )}
                            >
                              {oversized ? "tekrar-chunk" : "iyi"}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ─── Ingest panel ────────────────────────────── */}
        <Card className="bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <CloudUpload className="h-4 w-4 text-primary" />
              Doküman yükle
            </CardTitle>
            <CardDescription>
              PDF · DOCX · XLSX · MD · TXT · 🖼️ PNG/JPG/WEBP (≤ 25 MB).
              Görseller Gemini ile betimlenip aynı index'e eklenir. Sürükle-bırak veya seç.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              data-test="rag-dropzone"
              onDragEnter={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files.length) {
                  void onDrop(e.dataTransfer.files);
                }
              }}
              className={cn(
                "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-border bg-background/30",
              )}
            >
              <CloudUpload className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium">
                Dosyaları buraya bırakın
              </p>
              <p className="text-xs text-muted-foreground">veya</p>
              <div className="flex items-center gap-2">
                <label className="cursor-pointer">
                  <input
                    type="file"
                    multiple
                    className="hidden"
                    data-test="rag-file-input"
                    onChange={(e) => {
                      if (e.target.files?.length) {
                        void onDrop(e.target.files);
                      }
                    }}
                  />
                  <span className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
                    Dosya seç
                  </span>
                </label>
                <label className="cursor-pointer">
                  <input
                    type="file"
                    multiple
                    className="hidden"
                    data-test="rag-folder-input"
                    ref={(el) => {
                      // webkitdirectory isn't a typed React prop — set it imperatively
                      if (el) el.setAttribute("webkitdirectory", "");
                    }}
                    onChange={(e) => {
                      if (e.target.files?.length) {
                        void onDrop(e.target.files);
                      }
                    }}
                  />
                  <span className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted">
                    Klasör seç
                  </span>
                </label>
              </div>
              {uploading && (
                <p className="text-xs text-muted-foreground">
                  {uploadProgress
                    ? `Yükleniyor… ${uploadProgress.done}/${uploadProgress.total}`
                    : "Yükleniyor…"}
                </p>
              )}
            </div>

            <div className="mt-4">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Mevcut dokümanlar
              </h4>
              <ul className="space-y-1">
                {docs.map((d) => (
                  <li
                    key={d.id}
                    data-test="rag-doc-row"
                    className="flex items-center justify-between rounded-md border border-border bg-background/40 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FileText className="h-3 w-3 text-muted-foreground" />
                      <code className="truncate font-mono">{d.filename}</code>
                    </div>
                    <div className="ml-2 flex shrink-0 items-center gap-2">
                      <span className="text-muted-foreground">
                        {d.chunks} chunk · {formatSize(d.size_bytes)}
                      </span>
                      <button
                        type="button"
                        onClick={() => void deleteDoc(d.id)}
                        disabled={deletingId === d.id}
                        data-test="rag-doc-delete"
                        aria-label={`${d.filename} dokümanını sil`}
                        className="rounded p-1 text-muted-foreground transition-colors hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* ─── Query panel ─────────────────────────────── */}
        <Card className="bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Search className="h-4 w-4 text-primary" />
              Sorgu test
            </CardTitle>
            <CardDescription>
              BGE-M3 dense + opsiyonel cross-encoder rerank.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="örn. CTO geçen ay neyi onayladı?"
              className="w-full rounded-md border border-border bg-background p-2 text-sm outline-none focus:border-primary/50"
              data-test="rag-query-input"
            />
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <label className="flex items-center gap-1">
                <span className="text-muted-foreground">Top-K:</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value) || 5)}
                  className="w-16 rounded border border-border bg-background px-2 py-1"
                  data-test="rag-topk-input"
                />
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={hybrid}
                  onChange={(e) => setHybrid(e.target.checked)}
                  data-test="rag-rerank-toggle"
                />
                <span className="text-muted-foreground">Cross-encoder rerank</span>
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={wantAnswer}
                  onChange={(e) => setWantAnswer(e.target.checked)}
                  data-test="rag-answer-toggle"
                />
                <span className="text-muted-foreground">Cevap üret (LLM)</span>
              </label>
              {/* Unified-index modality filter — one search spans docs + images;
                  scope it here without a separate query. */}
              <div
                className="inline-flex overflow-hidden rounded-md border border-border"
                data-test="rag-kind-filter"
              >
                {([
                  ["all", "Tümü"],
                  ["docs", "📄 Doküman"],
                  ["images", "🖼️ Görsel"],
                ] as [KindFilter, string][]).map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setKindFilter(k)}
                    data-test={`rag-kind-${k}`}
                    className={cn(
                      "px-2 py-1 text-[11px] transition-colors",
                      kindFilter === k
                        ? "bg-primary text-primary-foreground"
                        : "bg-background text-muted-foreground hover:bg-muted",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                onClick={runQuery}
                disabled={searching || !query.trim()}
                data-test="rag-run-query"
              >
                {searching ? "Sorgulanıyor…" : "Sorguyu çalıştır"}
              </Button>
              {/* image-as-query: search the index using an uploaded image */}
              <label className="cursor-pointer">
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  data-test="rag-image-query-input"
                  disabled={searching}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void runImageQuery(f);
                    e.target.value = "";
                  }}
                />
                <span className="inline-flex items-center rounded-md border border-border px-3 py-2 text-xs font-medium hover:bg-muted">
                  🖼️ Görselle ara
                </span>
              </label>
            </div>

            {imgDesc && (
              <div
                data-test="rag-image-desc"
                className="rounded-md border border-violet-500/30 bg-violet-500/5 p-3 text-xs"
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-violet-300">
                  Görselden çıkarılan sorgu
                </div>
                <p className="text-foreground/90">{imgDesc}</p>
              </div>
            )}

            {error && (
              <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
                {error}
              </div>
            )}

            {answer && (
              <div
                data-test="rag-answer"
                className="rounded-md border border-primary/30 bg-primary/5 p-3"
              >
                <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                  <Sparkles className="h-3 w-3" />
                  Cevap
                </div>
                <p className="whitespace-pre-wrap text-xs text-foreground/90">
                  {answer}
                </p>
                <p className="mt-2 text-[10px] text-muted-foreground">
                  Aşağıdaki kaynaklardan üretildi — numaralar [n] kaynakları gösterir.
                </p>
              </div>
            )}

            {searching ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : hits.length > 0 ? (
              <ul className="space-y-2">
                {hits.map((h, i) => (
                  <li
                    key={`${h.chunk_id}-${i}`}
                    data-test="rag-hit-row"
                    className="rounded-md border border-border bg-background/40 p-3"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      {h.metadata?.kind === "image" ? (
                        <Badge
                          variant="outline"
                          className="border-violet-500/40 text-[10px] text-violet-300"
                          data-test="rag-hit-kind"
                        >
                          🖼️ Görsel
                          {h.metadata.source_filename
                            ? ` · ${h.metadata.source_filename}`
                            : ""}
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="border-sky-500/40 text-[10px] text-sky-300"
                          data-test="rag-hit-kind"
                        >
                          📄 Doküman
                        </Badge>
                      )}
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {h.doc_id}
                      </Badge>
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-[10px] text-emerald-300"
                      >
                        score {h.score.toFixed(2)}
                      </Badge>
                    </div>
                    <p className="text-xs text-foreground/90">
                      {h.metadata?.kind === "image" ? (
                        <span className="mr-1 text-[10px] uppercase tracking-wider text-violet-300/80">
                          görsel açıklaması:
                        </span>
                      ) : null}
                      {h.text}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* ── Ingestion sources · Pipeline · Security (mockup 06) ── */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="bg-card/60">
          <CardHeader className="pb-2"><CardTitle className="text-base">↓ İngestion Kaynakları</CardTitle></CardHeader>
          <CardContent className="space-y-1.5 text-[12px] text-muted-foreground">
            {[
              "Manual upload · Drive · SharePoint", "Website crawler (ToS-güvenli)",
              "CRM notes · Support tickets", "Call transcripts · Meeting notes",
              "Email threads · Notion · Confluence", "ERP product catalog · Proposal archive",
            ].map((s) => (<div key={s} className="flex items-start gap-2"><span className="text-emerald-400">✓</span><span>{s}</span></div>))}
          </CardContent>
        </Card>
        <Card className="bg-card/60">
          <CardHeader className="pb-2"><CardTitle className="text-base">⚙ Pipeline</CardTitle></CardHeader>
          <CardContent>
            <ol className="space-y-1.5 text-[12px] text-muted-foreground">
              {[
                "Extract (PDF/Word/Excel/HTML)", "Clean + PII detection + dil tespit",
                "Chunk (400c) + contextual prefix", "Embed (BGE-M3 GPU) + keyword index",
                "Graph linking + entity tag", "Quality validation + publish",
              ].map((s, i) => (<li key={s} className="flex gap-2"><span className="font-mono text-primary">{i + 1}</span><span>{s}</span></li>))}
            </ol>
          </CardContent>
        </Card>
        <Card className="bg-card/60">
          <CardHeader className="pb-2"><CardTitle className="text-base">⛨ RAG Güvenlik</CardTitle></CardHeader>
          <CardContent>
            <p className="text-[12px] leading-relaxed text-muted-foreground">
              tenant + role + department + sensitivity + PII + agent-allowed-source kontrolü → agentin görmemesi gereken doküman sonuca girmez.
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
