"""qual-code: Paralel (kimi + gpt-oss-20b) → codellama verify → gptoss-120b fix."""

from __future__ import annotations

import time

from app.pipelines.base import BasePipeline, PipelineResult, PipelineStep
from app.pipelines.execution import pick_longest_success, run_parallel_named, timed_step
from app.providers.registry import get_provider
from app.workflow.integration import WorkflowSession


def _step_payload(step: PipelineStep) -> dict:
    return {"model": step.model, "elapsed_ms": step.elapsed_ms, "ok": step.ok}


class QualCodePipeline(BasePipeline):
    pipeline_type = "qual-code"

    async def run(self, prompt: str) -> PipelineResult:
        total_start = time.monotonic()
        steps: list[PipelineStep] = []
        wf = WorkflowSession(self.pipeline_type, prompt)

        kimi = get_provider("cloudflare")
        groq = get_provider("groq")

        parallel_start = time.monotonic()
        drafts = await run_parallel_named(
            {
                "kimi": kimi.call(prompt, model="@cf/moonshotai/kimi-k2.5"),
                "gpt-oss-20b": groq.call(prompt, model="openai/gpt-oss-20b"),
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
            meta={"attempted": list(drafts.keys()), "succeeded": ok_names},
        )
        steps.append(parallel_step)
        wf.step("parallel-drafts", "ok" if parallel_step.ok else "fail", _step_payload(parallel_step))

        best = pick_longest_success(drafts)
        if best is None:
            wf.finish("fail")
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                steps=steps,
                final_response="",
                total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
                prompt=prompt,
                error="Tüm üretim adımları başarısız",
                workflow_trace_id=wf.trace_id,
            )
        _, draft = best

        ollama = get_provider("ollama")
        verify_prompt = (
            "Review this code for bugs, missing imports, syntax errors. "
            "List ONLY issues found, or say 'PASS' if no issues:\n\n"
            + draft.text[:4000]
        )
        verify_step, verify = await timed_step(
            "verify",
            ollama.call(verify_prompt, model="codellama:7b"),
            model_hint="codellama:7b",
        )
        steps.append(verify_step)
        wf.step("verify", "ok" if verify_step.ok else "fail", _step_payload(verify_step))

        final_text = draft.text
        if verify is not None and verify.text:
            vt = verify.text.upper()
            if "PASS" not in vt and len(vt) > 10:
                fix_prompt = (
                    "Fix these issues in the code:\n\n"
                    f"ISSUES:\n{verify.text[:1500]}\n\n"
                    f"ORIGINAL CODE:\n{draft.text[:6000]}\n\n"
                    "Return only the fixed code."
                )
                fix_step, fix = await timed_step(
                    "fix",
                    groq.call(fix_prompt, model="openai/gpt-oss-120b"),
                    model_hint="openai/gpt-oss-120b",
                )
                steps.append(fix_step)
                wf.step("fix", "ok" if fix_step.ok else "fail", _step_payload(fix_step))
                if fix is not None and fix.text:
                    final_text = fix.text

        wf.finish("ok")
        return PipelineResult(
            pipeline_type=self.pipeline_type,
            steps=steps,
            final_response=final_text,
            total_elapsed_ms=int((time.monotonic() - total_start) * 1000),
            prompt=prompt,
            workflow_trace_id=wf.trace_id,
        )
