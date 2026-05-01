// Q7 Phase C — premium /panel "Genel Bakış" home with Tremor charts.
"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Layers,
  Package,
  ShieldCheck,
} from "lucide-react";
import {
  AreaChart,
  BarList,
  Card as TremorCard,
  Title,
  Subtitle,
  Flex,
} from "@tremor/react";

import { StatCard } from "@/components/panel/StatCard";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface ToolsResponse {
  total?: number;
  category_counts?: Record<string, number>;
}

interface QuotaSlice {
  used: number;
  limit: number;
  percent: number;
  label: string;
}

interface QuotaResponse {
  claude_plus: QuotaSlice;
  free_providers?: Record<string, QuotaSlice>;
}

interface CascadePoint {
  ts: string;
  count: number;
}

interface CascadeResponse {
  count?: number;
  providers_active?: number;
  timeseries?: CascadePoint[];
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include", cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

export default function PanelHome() {
  const tools = useQuery({
    queryKey: ["panel", "tools"],
    queryFn: () => fetchJson<ToolsResponse>("/v1/panel/tools"),
  });
  const quota = useQuery({
    queryKey: ["panel", "quota"],
    queryFn: () => fetchJson<QuotaResponse>("/v1/system/quota_status"),
  });
  const cascade = useQuery({
    queryKey: ["panel", "cascade"],
    queryFn: () => fetchJson<CascadeResponse>("/v1/panel/cascade/recent"),
  });

  const toolsTotal = tools.data?.total ?? 0;
  const cascadeCount = cascade.data?.count ?? 0;
  const providersActive = cascade.data?.providers_active ?? 0;
  const claudePct = quota.data?.claude_plus
    ? Math.round(quota.data.claude_plus.percent * 100)
    : 0;
  const claudeUsed = quota.data?.claude_plus?.used ?? 0;
  const claudeLimit = quota.data?.claude_plus?.limit ?? 0;

  const categoryBars = Object.entries(tools.data?.category_counts ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const cascadeSeries = (cascade.data?.timeseries ?? []).map((p) => ({
    date: p.ts,
    Calls: p.count,
  }));

  return (
    <main
      data-page="panel-home"
      className="mx-auto w-full max-w-7xl px-6 py-10"
    >
      <motion.header
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-semibold tracking-tight">Genel Bakış</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          ABS Server kontrol merkezi — MCP araçları, cascade trafiği ve kota
          durumu.
        </p>
      </motion.header>

      <section
        data-test="panel-stats"
        className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <StatCard
          title="MCP Tools"
          value={tools.isLoading ? "…" : toolsTotal}
          hint={
            tools.data?.category_counts
              ? `${Object.keys(tools.data.category_counts).length} kategori`
              : "yükleniyor"
          }
          icon={Package}
          delay={0.0}
        />
        <StatCard
          title="Cascade (24h)"
          value={cascade.isLoading ? "…" : cascadeCount.toLocaleString("tr-TR")}
          hint={`${providersActive} aktif sağlayıcı`}
          icon={Activity}
          delay={0.05}
        />
        <StatCard
          title="Claude Quota"
          value={`${claudePct}%`}
          delta={
            claudeLimit > 0
              ? `${claudeUsed.toLocaleString("tr-TR")} / ${claudeLimit.toLocaleString("tr-TR")}`
              : undefined
          }
          deltaType={
            claudePct >= 95
              ? "decrease"
              : claudePct >= 80
                ? "neutral"
                : "increase"
          }
          icon={ShieldCheck}
          delay={0.1}
        />
        <StatCard
          title="Sağlayıcılar"
          value={providersActive}
          hint="cascade routing"
          icon={Layers}
          delay={0.15}
        />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.2 }}
          className="lg:col-span-2"
        >
          <Card className="bg-card/60 backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" />
                Cascade trafiği
              </CardTitle>
              <CardDescription>
                Son 24 saatlik MCP cascade çağrı sayısı.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {cascade.isLoading ? (
                <Skeleton className="h-64 w-full" />
              ) : cascadeSeries.length === 0 ? (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                  Veri yok
                </div>
              ) : (
                <AreaChart
                  className="h-64"
                  data={cascadeSeries}
                  index="date"
                  categories={["Calls"]}
                  colors={["indigo"]}
                  showAnimation
                  showLegend={false}
                  showGridLines={false}
                  curveType="monotone"
                  yAxisWidth={40}
                />
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.25 }}
        >
          <Card className="h-full bg-card/60 backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-primary" />
                Tool kategorileri
              </CardTitle>
              <CardDescription>
                MCP araç dağılımı (top 8 kategori).
              </CardDescription>
            </CardHeader>
            <CardContent>
              {tools.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-6 w-full" />
                  ))}
                </div>
              ) : categoryBars.length === 0 ? (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  Veri yok
                </div>
              ) : (
                <TremorCard className="border-0 bg-transparent p-0 shadow-none">
                  <Flex className="mb-2">
                    <Title className="text-xs uppercase tracking-wider text-muted-foreground">
                      Kategori
                    </Title>
                    <Subtitle className="text-xs uppercase tracking-wider text-muted-foreground">
                      Adet
                    </Subtitle>
                  </Flex>
                  <BarList data={categoryBars} color="indigo" />
                </TremorCard>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </section>

      {(tools.isError || quota.isError || cascade.isError) && (
        <p
          role="alert"
          className="mt-6 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
        >
          Bazı veriler yüklenemedi. Backend bağlantısını kontrol edin.
        </p>
      )}
    </main>
  );
}
