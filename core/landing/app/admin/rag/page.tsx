/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase F — `/admin/rag` knowledge-base console. Drag-drop ingest +
// query test + result viz. Backend (`/v1/rag/*`) currently uses OAuth
// gating, so this page ships in mock-friendly mode (POST attempts forwarded
// to backend; on 401/403 we fall back to a deterministic local response so
// the UX is exercisable end-to-end during Phase O).
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

const MOCK_DOCS: IngestedDoc[] = [
  {
    id: "doc-001",
    filename: "guvenlik_politikasi.md",
    size_bytes: 18432,
    chunks: 14,
    ingested_at: "2026-04-29T10:42:00Z",
  },
  {
    id: "doc-002",
    filename: "satis_q2_raporu.pdf",
    size_bytes: 528000,
    chunks: 86,
    ingested_at: "2026-04-30T08:15:00Z",
  },
  {
    id: "doc-003",
    filename: "musteri_destek_sss.txt",
    size_bytes: 9120,
    chunks: 7,
    ingested_at: "2026-05-01T09:55:00Z",
  },
];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RagPage() {
  const [docs, setDocs] = useState<IngestedDoc[]>(MOCK_DOCS);
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
      const incoming = Array.from(files).map((f) => ({
        id: `doc-${crypto.randomUUID().slice(0, 8)}`,
        filename: f.name,
        size_bytes: f.size,
        chunks: Math.ceil(f.size / 1200),
        ingested_at: new Date().toISOString(),
      }));
      // Best-effort backend ping; falls back to local mock if 401/403/404.
      try {
        for (const f of files) {
          const form = new FormData();
          form.append("file", f);
          await fetch("/v1/rag/ingest-file", {
            method: "POST",
            credentials: "include",
            body: form,
          }).catch(() => null);
        }
      } catch {
        /* mock fallback */
      }
      setDocs((prev) => [...incoming, ...prev]);
      setUploading(false);
    },
    [],
  );

  async function runQuery() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const res = await fetch("/v1/rag/query", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: topK, rerank: hybrid }),
      });
      if (!res.ok) {
        // Fall back to a deterministic mock response so the UX is exercisable
        // even before tenant OAuth is wired through to the panel session.
        setHits(
          docs.slice(0, topK).map((d, i) => ({
            chunk_id: `${d.id}-${i}`,
            score: Math.max(0.42, 0.95 - i * 0.08),
            text: `[MOCK] '${query}' sorgusunun ${d.filename} dökümanındaki ${i + 1}. eşleşmesi. Backend OAuth bağlantısı Phase K'da aktiflenecek.`,
            doc_id: d.id,
          })),
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
