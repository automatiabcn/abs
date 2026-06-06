"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle,
  Clock,
  FloppyDisk,
  FolderOpen,
  PaperPlaneTilt,
  Play,
  Spinner,
  ThumbsDown,
  ThumbsUp,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";

import WorkflowCanvasFlow from "@/components/WorkflowCanvasFlow";
import {
  estimateCostCents,
  isValidWorkflow,
  SAMPLE_WORKFLOW,
  type WorkflowDefinition,
} from "@/lib/workflow";

type DryRunStatus = "idle" | "running" | "ok" | "error";

interface SavedWorkflowRow {
  id: number;
  name: string;
  definition: WorkflowDefinition;
  updated_at?: string;
}

// /v1/workflows/execute response shapes (dry-run plan + queued job).
interface ExecuteStep {
  step: number;
  node_id: string;
  kind: string;
  name: string;
  estimate_s: number;
}

interface DryRunResult {
  steps: ExecuteStep[];
  estimate_s: number;
  estimated_cost_usd: number;
}

// /v1/workflows/jobs/{id} poll state.
interface JobState {
  job_id: string;
  state: string; // queued | running | awaiting_approval | done | error
  node_outputs: Record<string, unknown>;
  pending_node?: string | null;
  warnings?: string[];
  error?: string | null;
}

type RunPhase =
  | "idle"
  | "planning"
  | "queued"
  | "running"
  | "awaiting_approval"
  | "done"
  | "error";

const RUN_PHASE_LABEL: Record<RunPhase, string> = {
  idle: "Hazır",
  planning: "Planlanıyor…",
  queued: "Sıraya alındı…",
  running: "Çalışıyor…",
  awaiting_approval: "İnsan onayı bekleniyor",
  done: "Tamamlandı",
  error: "Hata",
};

// Best-effort one-line summary of a node's output for the result panel.
function nodeOutputSummary(out: unknown): string {
  if (out && typeof out === "object") {
    const o = out as Record<string, unknown>;
    if (typeof o.error === "string") return `⚠ ${o.error}`;
    if (typeof o.skipped === "string")
      return `↷ atlandı (${o.skipped})${o.note ? ` — ${o.note}` : ""}`;
    if (o.awaiting) return "⏳ onay bekleniyor";
    if (o.rejected === true) return "✕ reddedildi";
    if (o.approved === true) return "✓ onaylandı";
    if (typeof o.text === "string") return o.text;
    return JSON.stringify(o).slice(0, 240);
  }
  return String(out ?? "");
}

type SynthFn = (intent: string, current: WorkflowDefinition) => Promise<WorkflowDefinition>;

type Props = {
  initialWorkflow: WorkflowDefinition;
  isAdmin: boolean;
  synthesizeFn?: SynthFn;
  onDryRun?: (wf: WorkflowDefinition) => Promise<{ ok: boolean }>;
  onSave?: (wf: WorkflowDefinition) => void;
};

// Polish round R4 — admin console copy is Turkish-first.
const DRY_RUN_LABEL: Record<DryRunStatus, string> = {
  idle: "Bekliyor",
  running: "Çalışıyor",
  ok: "Başarılı",
  error: "Başarısız",
};

async function defaultSynthesize(
  intent: string,
  current: WorkflowDefinition,
): Promise<WorkflowDefinition> {
  const r = await fetch("/api/workflow/synthesize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent, current }),
  });
  if (!r.ok) {
    // 422 = request validation (the backend requires intent ≥ 10 chars). Give
    // a clear, actionable message instead of a raw status / "load sample".
    if (r.status === 422) {
      throw new Error(
        "İş akışını biraz daha ayrıntılı anlat (en az 10 karakter, tercihen tam bir cümle). Örn: \"Gmail mesajlarını sınıflandır ve satış etiketlilere yanıt taslağı hazırla\".",
      );
    }
    throw new Error(`synthesize failed: ${r.status}`);
  }
  // The backend returns the SynthesizeResponse envelope
  // ({ workflow, explanation, warnings, ... }) — NOT the bare workflow.
  // Unwrap `.workflow`; previously the whole envelope was cast as the
  // workflow, so `isValidWorkflow` always failed and the panel showed the
  // "örnek şablon yükle" CTA even on a perfectly good synthesis.
  const data = (await r.json()) as
    | { workflow?: WorkflowDefinition }
    | WorkflowDefinition;
  if (data && typeof data === "object" && "workflow" in data && data.workflow) {
    return data.workflow as WorkflowDefinition;
  }
  return data as WorkflowDefinition;
}

export default function WorkflowChatPanel({
  initialWorkflow,
  isAdmin,
  synthesizeFn,
  onDryRun,
  onSave,
}: Props) {
  const [workflow, setWorkflow] = useState<WorkflowDefinition>(initialWorkflow);
  const [intent, setIntent] = useState("");
  const [refineText, setRefineText] = useState("");
  const [synthesising, setSynthesising] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dryRunStatus, setDryRunStatus] = useState<DryRunStatus>("idle");
  const [selectedNodeId, setSelectedNodeId] = useState<string | undefined>();
  const [saveStatus, setSaveStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  // Saved-workflow library — fixes "I saved a workflow, where is it?": the
  // builder now lists the tenant's saved workflows and can reload/delete them.
  const [savedList, setSavedList] = useState<SavedWorkflowRow[]>([]);
  const [loadedId, setLoadedId] = useState<number | null>(null);
  // Execute / run state — turns the builder from "design only" into something
  // an operator can actually dry-run (plan + cost) and run for real (queued
  // job → live status polling → per-node output + HITL approval).
  const [runPhase, setRunPhase] = useState<RunPhase>("idle");
  const [dryResult, setDryResult] = useState<DryRunResult | null>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  // Guard against overlapping pollers (re-run while a previous one is alive).
  const pollAbort = useRef(0);

  const synth = synthesizeFn ?? defaultSynthesize;

  const refreshSaved = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const r = await fetch("/v1/workflows/definitions", {
        credentials: "include",
      });
      if (!r.ok) return;
      const data = await r.json();
      setSavedList(Array.isArray(data.workflows) ? data.workflows : []);
    } catch {
      /* best-effort — the list is non-critical */
    }
  }, [isAdmin]);

  useEffect(() => {
    void refreshSaved();
  }, [refreshSaved]);

  function loadSaved(row: SavedWorkflowRow) {
    setError(null);
    setSaveStatus("idle");
    if (isValidWorkflow(row.definition)) {
      setWorkflow(row.definition);
      setLoadedId(row.id);
    } else {
      setError("Kayıtlı iş akışı bozuk görünüyor (nodes/edges eksik).");
    }
  }

  async function deleteSaved(id: number) {
    try {
      const r = await fetch(`/v1/workflows/definitions/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!r.ok && r.status !== 204) return;
      if (loadedId === id) setLoadedId(null);
      await refreshSaved();
    } catch {
      /* best-effort */
    }
  }

  async function runSynthesize(text: string) {
    if (!text.trim()) return;
    setSynthesising(true);
    setError(null);
    try {
      const next = await synth(text, workflow);
      // Q8 / W2 fix — guard against empty/partial cascade responses so the
      // canvas never gets a workflow without `nodes`/`edges` arrays. When
      // the schema fails, keep the previous workflow on screen and surface
      // a retry-friendly error.
      if (!isValidWorkflow(next)) {
        throw new Error(
          "Sentezleyici eksik bir iş akışı döndürdü. Tekrar deneyin veya örnek şablonu yükleyin.",
        );
      }
      setWorkflow(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSynthesising(false);
    }
  }

  function loadSample() {
    setError(null);
    setWorkflow(SAMPLE_WORKFLOW);
  }

  async function postExecute(dryRun: boolean): Promise<Record<string, unknown>> {
    const r = await fetch("/v1/workflows/execute", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow, dry_run: dryRun }),
    });
    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      throw new Error(`HTTP ${r.status} ${detail.slice(0, 160)}`);
    }
    return (await r.json()) as Record<string, unknown>;
  }

  // Dry-run: backend plans the DAG + estimates time/cost without executing.
  async function handleDryRun() {
    if (!isAdmin) return;
    setDryRunStatus("running");
    setRunError(null);
    setRunPhase("planning");
    setDryResult(null);
    setJob(null);
    try {
      // Keep the parent-supplied onDryRun contract (used by tests / embeds);
      // otherwise hit the backend execute endpoint in dry-run mode.
      if (onDryRun) {
        const r = await onDryRun(workflow);
        setDryRunStatus(r?.ok ? "ok" : "error");
        setRunPhase(r?.ok ? "done" : "error");
        return;
      }
      const data = await postExecute(true);
      setDryResult({
        steps: (data.steps as ExecuteStep[]) ?? [],
        estimate_s: Number(data.estimate_s ?? 0),
        estimated_cost_usd: Number(data.estimated_cost_usd ?? 0),
      });
      setDryRunStatus("ok");
      setRunPhase("done");
    } catch (e) {
      setDryRunStatus("error");
      setRunPhase("error");
      setRunError(e instanceof Error ? e.message : String(e));
    }
  }

  async function pollJob(jobId: string, token: number) {
    // Poll until terminal (done/error) or paused (awaiting_approval).
    for (let i = 0; i < 150; i++) {
      if (pollAbort.current !== token) return; // superseded by a newer run
      await new Promise((res) => setTimeout(res, 800));
      if (pollAbort.current !== token) return;
      let st: JobState;
      try {
        const r = await fetch(`/v1/workflows/jobs/${jobId}`, {
          credentials: "include",
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        st = (await r.json()) as JobState;
      } catch (e) {
        setRunError(e instanceof Error ? e.message : String(e));
        setRunPhase("error");
        return;
      }
      setJob(st);
      if (st.state === "done") return setRunPhase("done");
      if (st.state === "error") {
        setRunError(st.error || "İş akışı hatayla sonlandı.");
        return setRunPhase("error");
      }
      if (st.state === "awaiting_approval")
        return setRunPhase("awaiting_approval");
      setRunPhase("running");
    }
    setRunError("Zaman aşımı — iş hâlâ çalışıyor olabilir.");
    setRunPhase("error");
  }

  // Real run: enqueue → poll live status. LLM/RAG/HTTP/output nodes execute;
  // side-effecting integrations (gmail_send, slack_post, …) honestly report
  // "not available" until a marketplace plugin is installed.
  async function runWorkflow() {
    if (!isAdmin) return;
    setRunError(null);
    setDryResult(null);
    setJob(null);
    setRunPhase("queued");
    const token = ++pollAbort.current;
    try {
      const data = await postExecute(false);
      const jobId = String(data.job_id ?? "");
      if (!jobId) throw new Error("Sunucu job_id döndürmedi.");
      setJob({ job_id: jobId, state: "queued", node_outputs: {} });
      await pollJob(jobId, token);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
      setRunPhase("error");
    }
  }

  async function resumeJob(approved: boolean) {
    if (!job?.job_id) return;
    setResuming(true);
    const token = ++pollAbort.current;
    try {
      const r = await fetch(`/v1/workflows/jobs/${job.job_id}/resume`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });
      if (!r.ok) {
        const detail = await r.text().catch(() => "");
        throw new Error(`HTTP ${r.status} ${detail.slice(0, 160)}`);
      }
      setRunPhase("running");
      await pollJob(job.job_id, token);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
      setRunPhase("error");
    } finally {
      setResuming(false);
    }
  }

  async function handleSave() {
    if (!isAdmin) return;
    // If a parent supplies onSave, defer to it (keeps the existing contract).
    if (onSave) {
      onSave(workflow);
      return;
    }
    // Otherwise persist directly — the Builder page renders this panel without
    // an onSave, so previously "Save" was a silent no-op (no saved workflows).
    setSaveStatus("saving");
    setError(null);
    // Update-in-place when a saved workflow is loaded (no duplicate rows),
    // otherwise create a new one and remember its id.
    const url = loadedId
      ? `/v1/workflows/definitions/${loadedId}`
      : "/v1/workflows/definitions";
    const method = loadedId ? "PUT" : "POST";
    try {
      const r = await fetch(url, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: workflow.name?.trim() || "İsimsiz iş akışı",
          definition: workflow,
        }),
      });
      if (!r.ok) {
        const detail = await r.text().catch(() => "");
        throw new Error(`Kaydedilemedi: HTTP ${r.status} ${detail.slice(0, 120)}`);
      }
      const saved = await r.json().catch(() => null);
      if (saved && typeof saved.id === "number") setLoadedId(saved.id);
      setSaveStatus("saved");
      await refreshSaved();
    } catch (e) {
      setSaveStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const costCents = estimateCostCents(workflow);
  const costLabel = `Çalıştırma başına tahmini maliyet: $${(costCents / 100).toFixed(2)}`;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <WorkflowCanvasFlow
          workflow={workflow}
          selectedNodeId={selectedNodeId}
          onSelectNode={(id) => setSelectedNodeId(id)}
          onWorkflowChange={(next) => setWorkflow(next)}
        />
      </div>

      <aside className="flex flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-5 ring-1 ring-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-zinc-50/10">
        <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
          Workflow&apos;unu anlat
        </h3>

        <textarea
          data-testid="intent-textarea"
          aria-label="Workflow intent"
          rows={4}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="örn. Gelen Gmail mesajlarını sınıflandır ve satış etiketli e-postalara yanıt taslağı hazırla."
          className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/5 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50"
        />

        {intent.trim().length > 0 && intent.trim().length < 10 && (
          <p className="-mt-2 text-xs text-amber-600 dark:text-amber-400">
            En az 10 karakter — biraz daha ayrıntılı anlat (tam bir cümle).
          </p>
        )}

        <button
          type="button"
          data-testid="synthesize-button"
          onClick={() => runSynthesize(intent)}
          disabled={synthesising || intent.trim().length < 10}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:enabled:bg-zinc-200"
        >
          {synthesising ? (
            <Spinner className="size-4 animate-spin" />
          ) : (
            <PaperPlaneTilt className="size-4" />
          )}
          Sentezle
        </button>

        {error && (
          <div
            data-testid="synthesize-error"
            className="flex flex-col gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-900 ring-1 ring-red-200 dark:bg-red-900/30 dark:text-red-200 dark:ring-red-800"
          >
            <div className="flex items-start gap-2">
              <WarningCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                data-testid="synthesize-retry"
                onClick={() => runSynthesize(intent || refineText)}
                className="rounded-md border border-red-300 px-2 py-1 text-[11px] font-medium hover:bg-red-100 dark:border-red-700 dark:hover:bg-red-900/50"
              >
                Tekrar dene
              </button>
              <button
                type="button"
                data-testid="synthesize-load-sample"
                onClick={loadSample}
                className="rounded-md border border-red-300 px-2 py-1 text-[11px] font-medium hover:bg-red-100 dark:border-red-700 dark:hover:bg-red-900/50"
              >
                Örnek şablonu yükle
              </button>
            </div>
          </div>
        )}

        <div
          data-testid="cost-preview"
          className="rounded-xl bg-zinc-50 p-3 text-xs text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:text-zinc-200 dark:ring-zinc-800"
        >
          {costLabel}
        </div>

        <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <label className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Düzenle
          </label>
          <textarea
            data-testid="refine-textarea"
            aria-label="Düzenle"
            rows={3}
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            placeholder="Göndermeden önce HITL (insan onayı) adımı ekle."
            className="mt-1 w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/5 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50"
          />
          <button
            type="button"
            data-testid="refine-button"
            onClick={() => runSynthesize(refineText)}
            disabled={synthesising || refineText.trim() === ""}
            className="mt-2 inline-flex w-full items-center justify-center rounded-xl border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Düzenlemeyi uygula
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            data-testid="dry-run-button"
            onClick={handleDryRun}
            disabled={!isAdmin || runPhase === "planning"}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {dryRunStatus === "ok" && <CheckCircle className="size-4 text-emerald-600" />}
            {dryRunStatus === "error" && <WarningCircle className="size-4 text-red-600" />}
            Kuru çalıştır
          </button>
          <button
            type="button"
            data-testid="run-button"
            onClick={runWorkflow}
            disabled={
              !isAdmin || runPhase === "queued" || runPhase === "running"
            }
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-emerald-500"
          >
            {runPhase === "queued" || runPhase === "running" ? (
              <Spinner className="size-4 animate-spin" />
            ) : (
              <Play className="size-4" weight="fill" />
            )}
            Çalıştır
          </button>
        </div>

        <button
          type="button"
          data-testid="save-button"
          onClick={handleSave}
          disabled={!isAdmin || saveStatus === "saving"}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:enabled:bg-zinc-200"
        >
          {saveStatus === "saved" ? (
            <CheckCircle className="size-4 text-emerald-400" />
          ) : (
            <FloppyDisk className="size-4" />
          )}
          {saveStatus === "saving"
            ? "Kaydediliyor…"
            : saveStatus === "saved"
              ? "Kaydedildi"
              : "Kaydet"}
        </button>

        <span
          data-testid="dry-run-status"
          className="text-xs font-medium text-zinc-600 dark:text-zinc-300"
        >
          {DRY_RUN_LABEL[dryRunStatus]}
        </span>

        {/* Run / dry-run result panel — plan + cost (dry) or live job status. */}
        {(runPhase !== "idle" || dryResult || job || runError) && (
          <div
            data-testid="run-result"
            className="flex flex-col gap-2 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex items-center gap-2 font-semibold text-zinc-700 dark:text-zinc-200">
              {runPhase === "running" || runPhase === "queued" ? (
                <Spinner className="size-4 animate-spin" />
              ) : runPhase === "done" ? (
                <CheckCircle className="size-4 text-emerald-600" />
              ) : runPhase === "error" ? (
                <WarningCircle className="size-4 text-red-600" />
              ) : runPhase === "awaiting_approval" ? (
                <Clock className="size-4 text-amber-500" />
              ) : (
                <Clock className="size-4" />
              )}
              {RUN_PHASE_LABEL[runPhase]}
            </div>

            {runError && (
              <p className="text-red-600 dark:text-red-400">{runError}</p>
            )}

            {/* Dry-run: plan + cost + time */}
            {dryResult && (
              <>
                <p className="text-zinc-600 dark:text-zinc-300">
                  {dryResult.steps.length} adım · ~{dryResult.estimate_s}s ·
                  tahmini ${dryResult.estimated_cost_usd.toFixed(4)}
                </p>
                <ol className="space-y-0.5">
                  {dryResult.steps.map((s) => (
                    <li
                      key={s.node_id}
                      className="flex items-center gap-2 text-zinc-600 dark:text-zinc-300"
                    >
                      <span className="text-zinc-400">{s.step}.</span>
                      <span className="font-medium">{s.name}</span>
                      <span className="rounded bg-zinc-200 px-1 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                        {s.kind}
                      </span>
                    </li>
                  ))}
                </ol>
              </>
            )}

            {/* Real run: per-node outputs */}
            {job && Object.keys(job.node_outputs ?? {}).length > 0 && (
              <ul className="space-y-1">
                {Object.entries(job.node_outputs).map(([nid, out]) => (
                  <li key={nid} className="flex flex-col gap-0.5">
                    <span className="font-mono text-[10px] text-zinc-400">
                      {nid}
                    </span>
                    <span className="whitespace-pre-wrap break-words text-zinc-700 dark:text-zinc-200">
                      {nodeOutputSummary(out).slice(0, 600)}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {/* HITL gate — approve / reject to resume the paused run */}
            {runPhase === "awaiting_approval" && (
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  data-testid="resume-approve"
                  onClick={() => void resumeJob(true)}
                  disabled={resuming}
                  className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1 font-medium text-white disabled:opacity-50 hover:enabled:bg-emerald-500"
                >
                  <ThumbsUp className="size-3.5" /> Onayla
                </button>
                <button
                  type="button"
                  data-testid="resume-reject"
                  onClick={() => void resumeJob(false)}
                  disabled={resuming}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 px-3 py-1 font-medium text-zinc-700 disabled:opacity-50 hover:enabled:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:enabled:bg-zinc-800"
                >
                  <ThumbsDown className="size-3.5" /> Reddet
                </button>
              </div>
            )}

            {job?.warnings && job.warnings.length > 0 && (
              <ul className="space-y-0.5 border-t border-zinc-200 pt-1 text-amber-600 dark:border-zinc-800 dark:text-amber-400">
                {job.warnings.map((w, i) => (
                  <li key={i}>⚠ {w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Saved workflow library — load / delete previously-saved workflows. */}
        <div
          data-testid="saved-workflows"
          className="mt-2 border-t border-zinc-200 pt-3 dark:border-zinc-800"
        >
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            <FolderOpen className="size-4" />
            Kayıtlı iş akışları
            {loadedId && (
              <span className="ml-auto rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                #{loadedId} yüklü
              </span>
            )}
          </div>
          {savedList.length === 0 ? (
            <p className="text-xs text-zinc-400">Henüz kayıtlı iş akışı yok.</p>
          ) : (
            <ul className="space-y-1">
              {savedList.map((w) => (
                <li
                  key={w.id}
                  data-testid="saved-workflow-row"
                  className={
                    "flex items-center justify-between rounded-lg border px-2 py-1.5 text-xs " +
                    (loadedId === w.id
                      ? "border-emerald-400/50 bg-emerald-500/5"
                      : "border-zinc-200 dark:border-zinc-800")
                  }
                >
                  <button
                    type="button"
                    data-testid="saved-workflow-load"
                    onClick={() => loadSaved(w)}
                    className="flex-1 truncate text-left text-zinc-800 hover:text-zinc-950 dark:text-zinc-200 dark:hover:text-white"
                    title={w.name}
                  >
                    {w.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`${w.name} sil`}
                    onClick={() => void deleteSaved(w.id)}
                    className="ml-2 rounded p-1 text-zinc-400 hover:text-red-500"
                  >
                    <Trash className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
