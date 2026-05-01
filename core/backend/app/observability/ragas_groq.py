"""Phase 7 / Q3 — Groq qwen32b LLM-judge backend for RAGAS evaluation.

Replaces the token-overlap mock (`_MockBackend`) with a real LLM-as-judge
that scores each `(question, answer, contexts)` tuple. Uses the OpenAI-
compatible Groq endpoint (free tier).

Setup:
  settings.groq_api_key  — required (8+ chars).
  settings.ragas_backend = "groq"  — toggle in `ragas_eval.get_evaluator`.
  ABS_RAGAS_GROQ_MODEL   — optional, defaults to `qwen-2.5-32b`.

Cost: $0 on Groq free tier (under TPD limit).

API surface mirrors `_MockBackend.evaluate(samples) -> EvalScores` so the
toggle is a one-line change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional, Sequence

import httpx

from app.config import settings
from app.observability.ragas_eval import EvalSample, EvalScores

logger = logging.getLogger(__name__)


GROQ_BASE_URL = os.environ.get("ABS_RAGAS_GROQ_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("ABS_RAGAS_GROQ_MODEL", "qwen/qwen3-32b")
JUDGE_TIMEOUT = float(os.environ.get("ABS_RAGAS_TIMEOUT_S", "30"))


_JUDGE_PROMPT = """You are evaluating a RAG (retrieval-augmented generation) answer.

Question: {question}

Retrieved contexts:
{contexts_block}

Generated answer: {answer}

Ground truth (if known): {ground_truth}

Score each metric in [0.0, 1.0]:
- faithfulness: does the answer make claims supported by the contexts only? (1.0 = fully grounded, 0.0 = invented)
- answer_relevance: does the answer address the question? (1.0 = directly answers, 0.0 = unrelated)
- context_precision: are the contexts relevant to the question? (1.0 = all relevant, 0.0 = noise)
- context_recall: do the contexts contain enough info for the ground truth? (1.0 = sufficient, 0.0 = missing)

Reply with ONLY a JSON object (no prose, no fences):
{{"faithfulness": <0..1>, "answer_relevance": <0..1>, "context_precision": <0..1>, "context_recall": <0..1>}}"""


def _build_prompt(sample: EvalSample) -> str:
    contexts = "\n".join(f"- {c}" for c in (sample.contexts or []))
    return _JUDGE_PROMPT.format(
        question=sample.question,
        contexts_block=contexts,
        answer=sample.answer,
        ground_truth=sample.ground_truth or "(not provided)",
    )


_NUMBER_RE = re.compile(r"-?\d*\.?\d+")


def _parse_score_dict(raw: str) -> dict[str, float]:
    """Parse JSON from the LLM reply; tolerate stray prose by extracting
    the first JSON object."""
    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


async def _judge_one(
    client: httpx.AsyncClient, sample: EvalSample
) -> dict[str, float]:
    prompt = _build_prompt(sample)
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    try:
        resp = await client.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=JUDGE_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("ragas_groq judge call failed: %s", exc)
        return {}
    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("ragas_groq malformed response: %s", exc)
        return {}
    return _parse_score_dict(content)


def _aggregate(per_sample: list[dict[str, float]]) -> EvalScores:
    keys = ("faithfulness", "answer_relevance", "context_precision", "context_recall")
    sums = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for row in per_sample:
        for k in keys:
            v = row.get(k)
            if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0:
                sums[k] += float(v)
                counts[k] += 1
    avg = {k: (sums[k] / counts[k]) if counts[k] else 0.0 for k in keys}
    return EvalScores(
        faithfulness=round(avg["faithfulness"], 4),
        answer_relevance=round(avg["answer_relevance"], 4),
        context_precision=round(avg["context_precision"], 4),
        context_recall=round(avg["context_recall"], 4),
        n_samples=len(per_sample),
    )


class GroqJudgeBackend:
    """Drop-in replacement for `_MockBackend` — concurrency-bounded so we
    don't exceed Groq's free-tier rate limit."""

    def __init__(self, max_concurrency: int = 4) -> None:
        self.max_concurrency = max_concurrency

    def evaluate(self, samples: Sequence[EvalSample]) -> EvalScores:
        return asyncio.run(self._evaluate_async(samples))

    async def _evaluate_async(
        self, samples: Sequence[EvalSample]
    ) -> EvalScores:
        if not samples:
            return EvalScores(0.0, 0.0, 0.0, 0.0, 0)
        if not settings.groq_api_key or len(settings.groq_api_key) < 8:
            raise RuntimeError(
                "ragas_groq: settings.groq_api_key not configured — set ABS_GROQ_API_KEY"
            )
        sem = asyncio.Semaphore(self.max_concurrency)

        async def gated(sample: EvalSample) -> dict[str, float]:
            async with sem:
                async with httpx.AsyncClient() as client:
                    return await _judge_one(client, sample)

        per_sample = await asyncio.gather(*(gated(s) for s in samples))
        return _aggregate(list(per_sample))


def get_groq_evaluator(max_concurrency: int = 4) -> GroqJudgeBackend:
    return GroqJudgeBackend(max_concurrency=max_concurrency)


__all__ = [
    "GroqJudgeBackend",
    "get_groq_evaluator",
]
