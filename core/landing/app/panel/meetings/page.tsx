// Q7 Phase C — premium /panel/meetings refactor (S20.5 behaviour preserved).
// Q9 Phase B — MT8 fix: filter bar (search + status + speaker count + date range).
"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { FilterX, Mic, RefreshCw, Search, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

interface MeetingRow {
  id: number;
  filename: string;
  duration_sec: number;
  speaker_count: number;
  status: "pending" | "done" | "error";
  summary: string;
  created_at: string;
  completed_at: string | null;
}

const ACCEPT = ".wav,.mp3,.m4a,.ogg,.flac,.webm";

function fmtDuration(sec: number): string {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      hour12: false,
      timeStyle: "short",
      dateStyle: "short",
    });
  } catch {
    return iso;
  }
}

function statusVariant(
  status: MeetingRow["status"],
): "success" | "destructive" | "secondary" {
  if (status === "done") return "success";
  if (status === "error") return "destructive";
  return "secondary";
}

type StatusFilter = "all" | MeetingRow["status"];

export default function MeetingsPanel() {
  const [meetings, setMeetings] = useState<MeetingRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Q9 / MT8 — filter state
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [minSpeakers, setMinSpeakers] = useState<number | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filtered = useMemo(() => {
    let list = meetings;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((m) => m.filename.toLowerCase().includes(q));
    }
    if (statusFilter !== "all") {
      list = list.filter((m) => m.status === statusFilter);
    }
    if (typeof minSpeakers === "number" && minSpeakers > 0) {
      list = list.filter((m) => m.speaker_count >= minSpeakers);
    }
    if (dateFrom) {
      const fromTs = new Date(dateFrom).getTime();
      list = list.filter((m) => new Date(m.created_at).getTime() >= fromTs);
    }
    if (dateTo) {
      // dateTo inclusive — push to end-of-day so 'today' captures all rows.
      const toTs = new Date(dateTo + "T23:59:59").getTime();
      list = list.filter((m) => new Date(m.created_at).getTime() <= toTs);
    }
    return list;
  }, [meetings, search, statusFilter, minSpeakers, dateFrom, dateTo]);

  const filtersActive =
    search !== "" ||
    statusFilter !== "all" ||
    minSpeakers !== "" ||
    dateFrom !== "" ||
    dateTo !== "";

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setMinSpeakers("");
    setDateFrom("");
    setDateTo("");
  };

  const fetchMeetings = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/v1/meetings", {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMeetings(data.meetings ?? []);
    } catch (exc) {
      setError(`Toplantılar yüklenemedi: ${(exc as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMeetings();
  }, []);

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("audio", file);
      const res = await fetch("/v1/meetings/upload", {
        method: "POST",
        body: form,
        credentials: "include",
      });
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail ?? `HTTP ${res.status}`)
          .catch(() => `HTTP ${res.status}`);
        throw new Error(detail);
      }
      await fetchMeetings();
    } catch (exc) {
      setError(`Yükleme başarısız: ${(exc as Error).message}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <main
      data-page="panel-meetings"
      className="mx-auto w-full max-w-6xl px-6 py-10 text-foreground"
    >
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Toplantılar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ses kaydını yükle — WhisperX large-v3 transkript ve speaker
          diarization üretir, kayıt SQLite&apos;a yazılır.
        </p>
      </header>

      <Card className="mb-8 bg-card/60 backdrop-blur">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-4 w-4 text-primary" />
            Yeni toplantı
          </CardTitle>
          <CardDescription>
            WAV / MP3 / M4A / OGG / FLAC / WEBM destekli.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label
            htmlFor="audio-upload"
            className="flex h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-background/40 text-sm text-muted-foreground transition hover:border-primary/60 hover:text-foreground"
            aria-busy={uploading}
          >
            <Upload className="h-5 w-5" />
            {uploading
              ? "Transkript ediliyor…"
              : "Ses dosyası seç veya buraya bırak"}
            <input
              id="audio-upload"
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              onChange={onFile}
              disabled={uploading}
              className="hidden"
            />
          </label>
        </CardContent>
      </Card>

      <Card className="bg-card/60 backdrop-blur">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div className="space-y-1">
            <CardTitle>Geçmiş</CardTitle>
            <CardDescription>
              Toplam {meetings.length} kayıt
              {filtersActive && (
                <>
                  {" · "}
                  <span className="text-primary">{filtered.length}</span>{" "}
                  filtreli
                </>
              )}
              {" · "}
              son güncelleme şimdi.
            </CardDescription>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={fetchMeetings}
            disabled={loading}
            data-test="meetings-refresh"
          >
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
            Yenile
          </Button>
        </CardHeader>
        <div
          data-test="meetings-filter-bar"
          className="grid grid-cols-2 gap-2 border-b border-border px-6 pb-4 sm:grid-cols-5"
        >
          <div className="relative col-span-2 sm:col-span-1">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Dosya adında ara…"
              data-test="meetings-filter-search"
              className="pl-7 text-xs"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            data-test="meetings-filter-status"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          >
            <option value="all">Tüm durumlar</option>
            <option value="pending">Beklemede</option>
            <option value="done">Tamamlandı</option>
            <option value="error">Hata</option>
          </select>
          <Input
            type="number"
            min={0}
            value={minSpeakers}
            onChange={(e) =>
              setMinSpeakers(e.target.value ? Number(e.target.value) : "")
            }
            placeholder="Min. konuşmacı"
            data-test="meetings-filter-speakers"
            className="text-xs"
          />
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            data-test="meetings-filter-from"
            className="text-xs"
          />
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            data-test="meetings-filter-to"
            className="text-xs"
          />
          {filtersActive && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              data-test="meetings-filter-clear"
              className="col-span-2 sm:col-span-5"
            >
              <FilterX className="mr-2 h-3.5 w-3.5" />
              Filtreleri temizle
            </Button>
          )}
        </div>
        <CardContent>
          {error && (
            <p
              role="alert"
              className="mb-4 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
            >
              {error}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="border-b border-border py-3 pr-3">Tarih</th>
                  <th className="border-b border-border py-3 pr-3">Dosya</th>
                  <th className="border-b border-border py-3 pr-3">Süre</th>
                  <th className="border-b border-border py-3 pr-3">Konuşmacı</th>
                  <th className="border-b border-border py-3 pr-3">Durum</th>
                  <th
                    className="border-b border-border py-3"
                    aria-hidden="true"
                  />
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <>
                    {Array.from({ length: 3 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={6} className="py-2">
                          <Skeleton className="h-6 w-full" />
                        </td>
                      </tr>
                    ))}
                  </>
                )}
                {!loading && filtered.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-6 text-center text-sm text-muted-foreground"
                    >
                      {meetings.length === 0
                        ? "Henüz toplantı yok. Yukarıdan ilk kaydı yükleyin."
                        : "Filtre ile eşleşen kayıt yok."}
                    </td>
                  </tr>
                )}
                {!loading &&
                  filtered.map((m) => (
                    <tr
                      key={m.id}
                      className="border-b border-border/50 transition-colors hover:bg-accent/40"
                    >
                      <td className="py-3 pr-3 font-mono text-xs text-muted-foreground">
                        {fmtDate(m.created_at)}
                      </td>
                      <td className="py-3 pr-3">{m.filename}</td>
                      <td className="py-3 pr-3 font-mono text-xs">
                        {fmtDuration(m.duration_sec)}
                      </td>
                      <td className="py-3 pr-3 font-mono text-xs">
                        {m.speaker_count}
                      </td>
                      <td className="py-3 pr-3">
                        <Badge
                          data-status={m.status}
                          variant={statusVariant(m.status)}
                        >
                          {m.status}
                        </Badge>
                      </td>
                      <td className="py-3">
                        <a
                          className="text-xs text-primary hover:underline"
                          href={`/panel/meetings/${m.id}`}
                        >
                          Detay
                        </a>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
