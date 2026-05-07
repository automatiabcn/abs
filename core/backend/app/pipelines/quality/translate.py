# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual-translate: qwen32b translate → kimi back-translate → llama compare → gptoss refine."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import timed_step
from app.providers.registry import get_provider
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualTranslatePipeline(BasePipeline):
    pipeline_type = "qual-translate"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        steps: list[PipelineStep] = []
        wf = WorkflowSession(self.pipeline_type, prompt)

        groq = get_provider("groq")
        cf = get_provider("cloudflare")
        ollama = get_provider("ollama")

        tr_step, tr = await timed_step(
            "translate",
            groq.call(prompt, model="qwen/qwen3-32b"),
            model_hint="qwen/qwen3-32b",
        )
        steps.append(tr_step)
        wf.step("translate", "ok" if tr_step.ok else "fail", _step_payload(tr_step))
        if tr is None or not tr.text:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error="Çeviri adımı başarısız",
                workflow_trace_id=wf.trace_id,
            )

        translated = tr.text
        back_prompt = "Translate back to the source language:\n\n" + translated[:3000]
        back_step, back = await timed_step(
            "back-translate",
            cf.call(back_prompt, model="@cf/moonshotai/kimi-k2.5"),
            model_hint="@cf/moonshotai/kimi-k2.5",
        )
        steps.append(back_step)
        wf.step("back-translate", "ok" if back_step.ok else "fail", _step_payload(back_step))

        final_text = translated
        if back is not None and back.text:
            compare_prompt = (
                "Bu iki metin aynı anlama mı geliyor? Anlam kaymasını listele:\n\n"
                f"ORIJINAL:\n{prompt[:2000]}\n\nGERİ-ÇEVRİLMİŞ:\n{back.text[:2000]}"
            )
            cmp_step, cmp_result = await timed_step(
                "compare",
                ollama.call(compare_prompt, model="llama3.1:8b"),
                model_hint="llama3.1:8b",
            )
            steps.append(cmp_step)
            wf.step("compare", "ok" if cmp_step.ok else "fail", _step_payload(cmp_step))

            if (
                cmp_result is not None
                and cmp_result.text
                and "TAMAM" not in cmp_result.text.upper()
                and len(cmp_result.text) > 20
            ):
                refine_prompt = (
                    "Çeviriyi iyileştir. Anlam kaymaları:\n"
                    f"{cmp_result.text[:1500]}\n\n"
                    f"Mevcut çeviri:\n{translated[:4000]}\n\n"
                    "Daha iyi çeviri döndür."
                )
                refine_step, refine = await timed_step(
                    "refine",
                    groq.call(refine_prompt, model="openai/gpt-oss-120b"),
                    model_hint="openai/gpt-oss-120b",
                )
                steps.append(refine_step)
                wf.step("refine", "ok" if refine_step.ok else "fail", _step_payload(refine_step))
                if refine is not None and refine.text:
                    final_text = refine.text

        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=final_text,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
