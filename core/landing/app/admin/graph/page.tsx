// Q8 Phase J — `/admin/graph` Neo4j console. Schema browser + Cypher
// query editor (monospace textarea, Monaco can ship in v2) + NL→Cypher
// helper + result table. Force-graph viz lands in Phase L when
// react-force-graph-3d is wired (cosmos replacement uses the same dep).
"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Brain,
  Database,
  PlayCircle,
  Sparkles,
  Upload,
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

interface SchemaResponse {
  node_labels?: string[];
  relationship_types?: string[];
  property_keys?: string[];
}

interface CypherResponse {
  rows: Record<string, unknown>[];
  elapsed_ms?: number;
  error?: string;
}

const SAMPLE_QUERIES: { label: string; cypher: string }[] = [
  {
    label: "Tüm Person node'ları",
    cypher: "MATCH (p:Person) RETURN p.name, p.email LIMIT 25",
  },
  {
    label: "Acme şirketi kontak ağı",
    cypher:
      "MATCH (c:Org {name: 'Acme'})<-[:WORKS_AT]-(p:Person) RETURN p.name, p.role",
  },
  {
    label: "Son hafta açılan ticket'lar",
    cypher:
      "MATCH (t:Ticket) WHERE t.created_at > datetime() - duration('P7D') RETURN t.id, t.title, t.severity",
  },
];

async function fetchSchema(): Promise<SchemaResponse> {
  const res = await fetch("/v1/graph/schema", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) return {};
  return res.json();
}

async function runCypher(cypher: string): Promise<CypherResponse> {
  try {
    const res = await fetch("/v1/graph/cypher", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cypher }),
    });
    if (!res.ok) {
      const text = await res.text();
      return { rows: [], error: text.slice(0, 400) || `HTTP ${res.status}` };
    }
    return res.json();
  } catch (exc) {
    return {
      rows: [],
      error: exc instanceof Error ? exc.message : "unknown",
    };
  }
}

async function nlToCypher(nl: string): Promise<string> {
  try {
    const res = await fetch("/v1/graph/nl-query", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: nl }),
    });
    if (!res.ok) {
      // Mock-friendly fallback when the live cascade isn't available.
      return `// [MOCK] '${nl}' için sentezlenen Cypher (Phase K canlı cascade ile değiştirilecek)\nMATCH (n) WHERE toLower(toString(n)) CONTAINS toLower('${nl.split(" ").slice(0, 3).join(" ")}') RETURN n LIMIT 10`;
    }
    const data = await res.json();
    return data.cypher ?? "";
  } catch {
    return `// [hata] NL→Cypher çağrısı başarısız\n// Backend Phase K'da settings tenant token ile aktiflenecek`;
  }
}

export default function GraphPage() {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [cypher, setCypher] = useState(SAMPLE_QUERIES[0].cypher);
  const [result, setResult] = useState<CypherResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [nl, setNl] = useState("");
  const [synthesising, setSynthesising] = useState(false);

  useEffect(() => {
    void fetchSchema().then(setSchema);
  }, []);

  async function handleRun() {
    setRunning(true);
    const r = await runCypher(cypher);
    setResult(r);
    setRunning(false);
  }

  async function handleNl() {
    if (!nl.trim()) return;
    setSynthesising(true);
    const generated = await nlToCypher(nl);
    setCypher(generated);
    setSynthesising(false);
  }

  const columns =
    result?.rows && result.rows.length > 0
      ? Object.keys(result.rows[0])
      : [];

  return (
    <main
      data-page="admin-graph"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Brain className="h-5 w-5 text-primary" />
          Knowledge Graph
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Neo4j 5 bolt — kurum graph'ı: kişiler, şirketler, projeler, ticket'lar.
          Cypher veya doğal dil ile sorgula.
        </p>
      </motion.header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
        {/* ─── Schema sidebar ──────────────────────────── */}
        <aside data-test="graph-schema" className="space-y-4">
          <Card className="bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Database className="h-4 w-4" />
                Şema
              </CardTitle>
            </CardHeader>
            <CardContent>
              {schema === null ? (
                <Skeleton className="h-24 w-full" />
              ) : (
                <div className="space-y-3 text-xs">
                  <div>
                    <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">
                      Node etiketleri
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(schema.node_labels ?? ["Person", "Org", "Project", "Ticket"]).map(
                        (l) => (
                          <Badge key={l} variant="outline" className="font-mono">
                            {l}
                          </Badge>
                        ),
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">
                      İlişki tipleri
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(schema.relationship_types ?? ["WORKS_AT", "OWNS", "MANAGES", "ASSIGNED_TO"]).map(
                        (r) => (
                          <Badge
                            key={r}
                            variant="outline"
                            className="font-mono text-[10px]"
                          >
                            -[:{r}]-
                          </Badge>
                        ),
                      )}
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Hazır sorgular</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {SAMPLE_QUERIES.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  onClick={() => setCypher(q.cypher)}
                  data-test="graph-sample-query"
                  className="block w-full rounded-md px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  {q.label}
                </button>
              ))}
            </CardContent>
          </Card>
        </aside>

        {/* ─── Editor + result ─────────────────────────── */}
        <section className="space-y-4">
          <Card className="bg-card/70">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Cypher editörü</CardTitle>
              <CardDescription>
                Neo4j 5 syntax. Read-only kullanıcılar yalnız MATCH/RETURN
                çalıştırabilir (Phase K'da role-based gate).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <textarea
                rows={6}
                value={cypher}
                onChange={(e) => setCypher(e.target.value)}
                spellCheck={false}
                data-test="graph-cypher-input"
                className="w-full rounded-md border border-border bg-background p-3 font-mono text-xs leading-relaxed outline-none focus:border-primary/50"
              />
              <div className="mt-3 flex items-center gap-2">
                <Button
                  type="button"
                  onClick={handleRun}
                  disabled={running || !cypher.trim()}
                  data-test="graph-run-cypher"
                >
                  <PlayCircle className="mr-2 h-4 w-4" />
                  {running ? "Çalıştırılıyor…" : "Çalıştır"}
                </Button>
                <span className="text-xs text-muted-foreground">
                  Sonuç hem tablo hem (Phase L) force-graph olarak görünür.
                </span>
              </div>
            </CardContent>
          </Card>

          {/* NL → Cypher */}
          <Card className="bg-card/70">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-primary" />
                Doğal dil sorgu
              </CardTitle>
              <CardDescription>
                Türkçe yazın, cascade Cypher'a çevirsin.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <input
                type="text"
                value={nl}
                onChange={(e) => setNl(e.target.value)}
                placeholder="örn. Acme şirketinde çalışan tüm kişileri bul"
                className="w-full rounded-md border border-border bg-background p-2 text-sm outline-none focus:border-primary/50"
                data-test="graph-nl-input"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleNl}
                disabled={synthesising || !nl.trim()}
                data-test="graph-nl-run"
              >
                <Upload className="mr-2 h-3 w-3" />
                {synthesising ? "Sentezleniyor…" : "Cypher üret"}
              </Button>
            </CardContent>
          </Card>

          {/* Result */}
          <Card className="bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Sonuç</CardTitle>
              {result?.elapsed_ms != null && (
                <CardDescription>
                  {result.rows.length} satır · {result.elapsed_ms.toFixed(0)} ms
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>
              {!result ? (
                <p className="text-sm text-muted-foreground">
                  Henüz sorgu çalıştırılmadı.
                </p>
              ) : result.error ? (
                <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
                  {result.error}
                </div>
              ) : result.rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Sorgu boş döndü.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50">
                      <tr>
                        {columns.map((c) => (
                          <th
                            key={c}
                            className="px-3 py-2 text-left font-mono text-muted-foreground"
                          >
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr
                          key={i}
                          data-test="graph-result-row"
                          className="border-t border-border"
                        >
                          {columns.map((c) => (
                            <td key={c} className="px-3 py-2 font-mono">
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
