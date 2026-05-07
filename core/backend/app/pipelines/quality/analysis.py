# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual-analysis: 3 paralel perspektif (technical/strategic/critical) → gptoss-120b sentez."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import run_parallel_named, timed_step
from app.providers.registry import get_provider
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualAnalysisPipeline(BasePipeline):
    pipeline_type = "qual-analysis"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        steps: list[PipelineStep] = []
        wf = WorkflowSession(self.pipeline_type, prompt)

        groq = get_provider("groq")
        cf = get_provider("cloudflare")
        gemini = get_provider("gemini")

        angle_tech = (
            "Analyze from a TECHNICAL perspective. Be specific and structured:\n\n"
            + prompt
        )
        angle_strat = (
            "Analyze from a STRATEGIC/BUSINESS perspective. Consider pros, cons, risks:\n\n"
            + prompt
        )
        angle_crit = (
            "Play devil's advocate. Find weaknesses, risks, and counter-arguments:\n\n"
            + prompt
        )

        parallel_start = time.monotonic()
        perspectives = await run_parallel_named(
            {
                "technical": groq.call(angle_tech, model="openai/gpt-oss-120b"),
                "strategic": cf.call(angle_strat, model="@cf/moonshotai/kimi-k2.5"),
                "critical": gemini.call(angle_crit, model="gemini-2.5-pro"),
            }
        )
        parallel_ms = int((time.monotonic() - parallel_start) * 1000)
        ok_names = [
            n
            for n, r in perspectives.items()
            if not isinstance(r, BaseException) and getattr(r, "text", "")
        ]
        parallel_step = PipelineStep(
            name="3-perspectives",
            model="+".join(ok_names) or "-",
            elapsed_ms=parallel_ms,
            ok=bool(ok_names),
            meta={"succeeded": ok_names},
        )
        steps.append(parallel_step)
        wf.step("3-perspectives", "ok" if parallel_step.ok else "fail", _step_payload(parallel_step))

        if not ok_names:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error="3 perspektif de başarısız",
                workflow_trace_id=wf.trace_id,
            )

        combined = "\n\n".join(
            f"=== {n.upper()} ===\n{perspectives[n].text[:2500]}" for n in ok_names
        )
        synth_prompt = (
            "Farklı açılardan yapılan bu analizleri sentezleyen bir rapor oluştur. "
            "Ortak noktalar, çelişkiler, öneriler:\n\n" + combined
        )
        synth_step, synth = await timed_step(
            "synthesis",
            groq.call(synth_prompt, model="openai/gpt-oss-120b"),
            model_hint="openai/gpt-oss-120b",
        )
        steps.append(synth_step)
        wf.step("synthesis", "ok" if synth_step.ok else "fail", _step_payload(synth_step))

        final_text = synth.text if synth and synth.text else combined
        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=final_text,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
