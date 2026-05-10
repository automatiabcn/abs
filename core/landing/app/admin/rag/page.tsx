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

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import {
  CloudUpload,
  Database,
  FileText,
  Search,
  Sparkles,
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
}

// BUG-27 — local-only inventory; docs are appended after a real
// `/v1/rag/ingest-file` POST returns 200. We no longer pre-seed with mock
// rows so the operator can see at a glance whether their tenant has any
// actual chunks indexed.
const INITIAL_DOCS: IngestedDoc[] = [];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RagPage() {
  const [docs, setDocs] = useState<IngestedDoc[]>(INITIAL_DOCS);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [hybrid, setHybrid] = useState(false);
  const [hits, setHits] = useState<RagHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    async (files: FileList) => {
      setUploading(true);
      setError(null);
      // BUG-27 — POST every file to /v1/rag/ingest individually so a single
      // failed upload doesn't poison the rest of the batch. Successful rows
      // are appended with the doc_id + chunk count returned by the backend
      // so the operator sees real chunk math, not estimated `size / 1200`.
      const successes: IngestedDoc[] = [];
      const failures: string[] = [];
      for (const file of Array.from(files)) {
        const text = await file.text().catch(() => "");
        if (!text.trim()) {
          failures.push(`${file.name}: boş dosya`);
          continue;
        }
        try {
          const res = await fetch("/v1/rag/ingest", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text,
              filename: file.name,
              mime_type: file.type || "text/plain",
            }),
          });
          if (!res.ok) {
            const detail = await res.text().catch(() => "");
            failures.push(
              `${file.name}: HTTP ${res.status} ${detail.slice(0, 120)}`,
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
        }
      }
      if (failures.length > 0) {
        setError(`Yükleme hatası: ${failures.join(" · ")}`);
      }
      if (successes.length > 0) {
        setDocs((prev) => [...successes, ...prev]);
      }
      setUploading(false);
    },
    [],
  );

  async function runQuery() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setHits([]);
    try {
      const res = await fetch("/v1/rag/query", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: topK, rerank: hybrid }),
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
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "unknown");
    } finally {
      setSearching(false);
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ─── Ingest panel ────────────────────────────── */}
        <Card className="bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <CloudUpload className="h-4 w-4 text-primary" />
              Doküman yükle
            </CardTitle>
            <CardDescription>
              PDF · MD · TXT · DOCX (≤ 25 MB). Sürükle-bırak veya seç.
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
              {uploading && (
                <p className="text-xs text-muted-foreground">Yükleniyor…</p>
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
                    <span className="ml-2 shrink-0 text-muted-foreground">
                      {d.chunks} chunk · {formatSize(d.size_bytes)}
                    </span>
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
            </div>
            <Button
              type="button"
              onClick={runQuery}
              disabled={searching || !query.trim()}
              data-test="rag-run-query"
            >
              {searching ? "Sorgulanıyor…" : "Sorguyu çalıştır"}
            </Button>

            {error && (
              <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
                {error}
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
                    <div className="mb-1 flex items-center gap-2">
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
                    <p className="text-xs text-foreground/90">{h.text}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
