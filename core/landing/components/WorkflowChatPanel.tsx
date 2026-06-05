"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import { useState } from "react";
import {
  CheckCircle,
  FloppyDisk,
  PaperPlaneTilt,
  Spinner,
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
    throw new Error(`synthesize failed: ${r.status}`);
  }
  return (await r.json()) as WorkflowDefinition;
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

  const synth = synthesizeFn ?? defaultSynthesize;

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

  async function handleDryRun() {
    if (!isAdmin) return;
    setDryRunStatus("running");
    try {
      const r = await onDryRun?.(workflow);
      setDryRunStatus(r?.ok ? "ok" : "error");
    } catch {
      setDryRunStatus("error");
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
    try {
      const r = await fetch("/v1/workflows/definitions", {
        method: "POST",
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
      setSaveStatus("saved");
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

        <button
          type="button"
          data-testid="synthesize-button"
          onClick={() => runSynthesize(intent)}
          disabled={synthesising || intent.trim() === ""}
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
            disabled={!isAdmin || dryRunStatus === "running"}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {dryRunStatus === "ok" && <CheckCircle className="size-4 text-emerald-600" />}
            {dryRunStatus === "error" && <WarningCircle className="size-4 text-red-600" />}
            Kuru çalıştır
          </button>
          <button
            type="button"
            data-testid="save-button"
            onClick={handleSave}
            disabled={!isAdmin || saveStatus === "saving"}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:enabled:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:enabled:bg-zinc-200"
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
        </div>

        <span
          data-testid="dry-run-status"
          className="text-xs font-medium text-zinc-600 dark:text-zinc-300"
        >
          {DRY_RUN_LABEL[dryRunStatus]}
        </span>
      </aside>
    </div>
  );
}
