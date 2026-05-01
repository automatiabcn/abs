"""qual_code_human: qual-code + comment/kodu 'insan izi' taşıyacak şekilde rewrite."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import timed_step
from app.pipelines.quality.code import QualCodePipeline
from app.providers.registry import get_provider
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualCodeHumanPipeline(BasePipeline):
    pipeline_type = "qual-code-human"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        wf = WorkflowSession(self.pipeline_type, prompt)

        code_result = await QualCodePipeline().run(prompt)
        steps = list(code_result.steps)
        wf.step(
            "qual-code",
            "ok" if not code_result.error else "fail",
            {"nested_trace_id": code_result.workflow_trace_id, "step_count": len(code_result.steps)},
        )

        text = code_result.final_response
        if not text:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error=code_result.error or "qual-code boş döndü",
                workflow_trace_id=wf.trace_id,
            )

        humanize_prompt = (
            "Bu kodu sıfırdan yazmış bir insan yazar gibi yeniden düzenle. "
            "Gereksiz AI-stili yorum satırlarını kaldır (ör. 'Bu fonksiyon ...', "
            "'# Step 1: ...'), değişken adlarını daha özgün yap, anlamı koru. "
            "Kod çalışır durumda kalmalı.\n\nKOD:\n" + text[:6000]
        )
        provider = get_provider("cloudflare")
        step, resp = await timed_step(
            "code-humanize",
            provider.call(humanize_prompt, model="@cf/moonshotai/kimi-k2.5"),
            model_hint="@cf/moonshotai/kimi-k2.5",
        )
        steps.append(step)
        wf.step("code-humanize", "ok" if step.ok else "fail", _step_payload(step))
        final = resp.text if resp and resp.text else text

        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=final,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
