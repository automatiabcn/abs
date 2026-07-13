# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual-tr: Paralel (qwen32b + gemini) → aya/llama review → kimi2 polish."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import pick_longest_success, run_parallel_named, timed_step
from app.providers.registry import get_provider
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualTrPipeline(BasePipeline):
    pipeline_type = "qual-tr"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        steps: list[PipelineStep] = []
        wf = WorkflowSession(self.pipeline_type, prompt)

        groq = get_provider("groq")
        gemini = get_provider("gemini")
        ollama = get_provider("ollama")
        cf = get_provider("cloudflare")

        parallel_start = time.monotonic()
        drafts = await run_parallel_named(
            {
                "qwen32b": groq.call(prompt, model="qwen/qwen3-32b"),
                "gemini": gemini.call(prompt, model="gemini-2.5-flash"),
            }
        )
        parallel_ms = int((time.monotonic() - parallel_start) * 1000)
        ok_names = [
            n
            for n, r in drafts.items()
            if not isinstance(r, BaseException) and getattr(r, "text", "")
        ]
        parallel_step = PipelineStep(
            name="parallel-drafts",
            model="+".join(ok_names) or "-",
            elapsed_ms=parallel_ms,
            ok=bool(ok_names),
            meta={"succeeded": ok_names},
        )
        steps.append(parallel_step)
        wf.step(
            "parallel-drafts",
            "ok" if parallel_step.ok else "fail",
            _step_payload(parallel_step),
        )

        best = pick_longest_success(drafts)
        if best is None:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error="Turkish generation failed",
                workflow_trace_id=wf.trace_id,
            )
        _, draft = best

        review_prompt = (
            "Check this Turkish text for grammar, fluency and consistency. "
            "List the problems, or reply 'TAMAM' if there are none:\n\n"
            + draft.text[:4000]
        )
        review_step, review = await timed_step(
            "review", ollama.call(review_prompt, model="aya:8b"), model_hint="aya:8b"
        )
        steps.append(review_step)
        wf.step(
            "review", "ok" if review_step.ok else "fail", _step_payload(review_step)
        )

        final_text = draft.text
        if review is not None and review.text:
            rt = review.text.upper()
            if "TAMAM" not in rt and "OK" not in rt and len(rt) > 10:
                polish_prompt = (
                    "Improve this Turkish text. Problems found:\n"
                    f"{review.text[:1500]}\n\n"
                    f"Orijinal metin:\n{draft.text[:6000]}\n\n"
                    "Return the corrected Turkish text."
                )
                polish_step, polish = await timed_step(
                    "polish",
                    cf.call(polish_prompt, model="@cf/moonshotai/kimi-k2.5"),
                    model_hint="@cf/moonshotai/kimi-k2.5",
                )
                steps.append(polish_step)
                wf.step(
                    "polish",
                    "ok" if polish_step.ok else "fail",
                    _step_payload(polish_step),
                )
                if polish is not None and polish.text:
                    final_text = polish.text

        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=final_text,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
