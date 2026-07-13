# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Qual_human: runs the qual-tr output through the humanize chain."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import timed_step
from app.pipelines.humanize.scorer import humanize_score_text
from app.pipelines.humanize.transformer import humanize_transform
from app.pipelines.quality.turkish import QualTrPipeline
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualHumanPipeline(BasePipeline):
    pipeline_type = "qual-human"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        wf = WorkflowSession(self.pipeline_type, prompt)

        # 1) qual-tr (nested pipeline — kendi workflow'unu yazar veya wf_durable off ise yazmaz)
        tr_result = await QualTrPipeline().run(prompt)
        steps = list(tr_result.steps)
        wf.step(
            "qual-tr",
            "ok" if not tr_result.error else "fail",
            {
                "nested_trace_id": tr_result.workflow_trace_id,
                "step_count": len(tr_result.steps),
            },
        )

        text = tr_result.final_response
        if not text:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error=tr_result.error or "qual-tr returned nothing",
                workflow_trace_id=wf.trace_id,
            )

        # 2) humanize score (before)
        before = humanize_score_text(text)
        before_step = PipelineStep(
            name="humanize-score",
            model="heuristic",
            elapsed_ms=0,
            ok=True,
            meta={"before_score": before.score, "matches": before.matches},
        )
        steps.append(before_step)
        wf.step("humanize-score-before", "ok", {"score": before.score})

        # 3) transform
        transform_step, new_text = await timed_step(
            "humanize-transform",
            humanize_transform(text, lang="tr"),
            model_hint="@cf/moonshotai/kimi-k2.5",
        )
        steps.append(transform_step)
        wf.step(
            "humanize-transform",
            "ok" if transform_step.ok else "fail",
            _step_payload(transform_step),
        )
        if not new_text:
            new_text = text

        # 4) humanize score (after)
        after = humanize_score_text(new_text)
        after_step = PipelineStep(
            name="humanize-score",
            model="heuristic",
            elapsed_ms=0,
            ok=True,
            meta={"after_score": after.score},
        )
        steps.append(after_step)
        wf.step("humanize-score-after", "ok", {"score": after.score})

        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=new_text,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
