# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-024 — RAGAS-style evaluation for CI gates (mock + deferred ragas SDK).

Mock backend works offline so the CI gate runs every PR without GPU. Real
`ragas` backend gated behind a deferred import. `regression_check` returns a
list of human-readable failures the CI workflow surfaces as `::error::`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "EvalSample",
    "EvalScores",
    "RagasEvaluator",
    "close_evaluator",
    "get_evaluator",
    "load_baseline",
    "regression_check",
    "save_baseline",
]

_STOPWORDS = {"the", "a", "of", "to", "is", "and", "for", "in"}


def _tokens(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", text.lower()).split()


@dataclass(slots=True)
class EvalSample:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None


@dataclass(slots=True)
class EvalScores:
    faithfulness: float
    answer_relevance: float
    context_precision: float
    context_recall: float
    n_samples: int


class _MockBackend:
    def __init__(self) -> None:
        logger.info("ragas_mock_init")

    def evaluate(self, samples: Sequence[EvalSample]) -> EvalScores:
        if not samples:
            return EvalScores(0.0, 0.0, 0.0, 0.0, 0)

        faiths: list[float] = []
        relevs: list[float] = []
        precs: list[float] = []
        recs: list[float] = []

        for s in samples:
            answer_tokens = _tokens(s.answer)
            ctx_tokens: set[str] = set()
            for c in s.contexts:
                ctx_tokens.update(_tokens(c))
            faiths.append(
                sum(1 for t in answer_tokens if t in ctx_tokens) / len(answer_tokens)
                if answer_tokens
                else 0.0
            )

            q_tokens = set(_tokens(s.question))
            a_set = set(answer_tokens)
            union = q_tokens | a_set
            relevs.append(len(q_tokens & a_set) / len(union) if union else 0.0)

            # Substring check uses raw words (preserving punctuation in the
            # original text) so hyphenated answers still match hyphenated
            # contexts.
            raw_first_four = " ".join(s.answer.lower().split()[:4])
            if not s.contexts or not raw_first_four:
                precs.append(0.0)
            elif raw_first_four in s.contexts[0].lower():
                precs.append(1.0)
            elif any(raw_first_four in c.lower() for c in s.contexts):
                precs.append(0.5)
            else:
                precs.append(0.0)

            if s.ground_truth:
                gt = [t for t in _tokens(s.ground_truth) if t not in _STOPWORDS]
                recs.append(
                    sum(1 for t in gt if t in ctx_tokens) / len(gt) if gt else 0.0
                )
            else:
                recs.append(faiths[-1])

        n = len(samples)
        return EvalScores(
            faithfulness=sum(faiths) / n,
            answer_relevance=sum(relevs) / n,
            context_precision=sum(precs) / n,
            context_recall=sum(recs) / n,
            n_samples=n,
        )

    def close(self) -> None:
        return None


class _RagasBackend:
    def __init__(self) -> None:
        try:
            from ragas import evaluate as _ev  # noqa: F401
            from ragas.metrics import (  # noqa: F401
                AnswerRelevancy,
                ContextPrecision,
                ContextRecall,
                Faithfulness,
            )
        except ImportError as exc:
            raise ImportError(
                "ragas backend requires `pip install ragas`"
            ) from exc
        from ragas import evaluate as _ev
        from ragas.metrics import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        self._evaluate = _ev
        self._metrics = [
            Faithfulness(),
            AnswerRelevancy(),
            ContextPrecision(),
            ContextRecall(),
        ]
        logger.info("ragas_sdk_init")

    def evaluate(self, samples: Sequence[EvalSample]) -> EvalScores:
        dataset = [
            {
                "question": s.question,
                "answer": s.answer,
                "contexts": s.contexts,
                "ground_truth": s.ground_truth or "",
            }
            for s in samples
        ]
        result = self._evaluate(dataset, metrics=self._metrics)
        try:
            import pandas as pd  # type: ignore[import]

            if isinstance(result, pd.DataFrame):
                m = result.mean()
                return EvalScores(
                    faithfulness=float(m.get("faithfulness", 0.0)),
                    answer_relevance=float(m.get("answer_relevancy", 0.0)),
                    context_precision=float(m.get("context_precision", 0.0)),
                    context_recall=float(m.get("context_recall", 0.0)),
                    n_samples=len(samples),
                )
        except Exception:  # noqa: BLE001
            logger.exception("ragas_result_parse_failed")
        return EvalScores(0.0, 0.0, 0.0, 0.0, len(samples))

    def close(self) -> None:
        return None


class RagasEvaluator:
    backend: str

    def __init__(self, backend: str | None = None) -> None:
        backend = backend or getattr(settings, "ragas_backend", "mock") or "mock"
        self.backend = backend
        if backend == "mock":
            self._impl = _MockBackend()
        elif backend == "ragas":
            self._impl = _RagasBackend()
        else:
            raise ValueError(f"unsupported ragas backend: {backend}")

    def evaluate(self, samples: list[EvalSample]) -> EvalScores:
        scores = self._impl.evaluate(samples)
        logger.debug(
            "ragas_eval n=%d faith=%.3f rel=%.3f prec=%.3f rec=%.3f",
            scores.n_samples,
            scores.faithfulness,
            scores.answer_relevance,
            scores.context_precision,
            scores.context_recall,
        )
        return scores

    def close(self) -> None:
        try:
            self._impl.close()
        except Exception:  # noqa: BLE001
            logger.exception("ragas_close_failed")


_evaluator: RagasEvaluator | None = None


def get_evaluator() -> RagasEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = RagasEvaluator()
    return _evaluator


def close_evaluator() -> None:
    global _evaluator
    if _evaluator is None:
        return
    try:
        _evaluator.close()
    finally:
        _evaluator = None


def regression_check(
    current: EvalScores,
    baseline: EvalScores,
    *,
    max_drop: float = 0.05,
) -> list[str]:
    failures: list[str] = []
    # 1e-9 tolerance absorbs FP rounding (0.9 - 0.85 == 0.05000000000000004).
    epsilon = 1e-9
    for name in ("faithfulness", "answer_relevance", "context_precision", "context_recall"):
        cur = float(getattr(current, name))
        base = float(getattr(baseline, name))
        if base - cur > max_drop + epsilon:
            msg = f"{name} dropped {base:.3f} → {cur:.3f} (> {max_drop:.3f})"
            failures.append(msg)
            logger.warning("ragas_regression %s", msg)
    return failures


def save_baseline(path: str | Path, scores: EvalScores) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "faithfulness": scores.faithfulness,
        "answer_relevance": scores.answer_relevance,
        "context_precision": scores.context_precision,
        "context_recall": scores.context_recall,
        "n_samples": scores.n_samples,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
    }
    p.write_text(json.dumps(payload, indent=2))
    logger.info("ragas_baseline_saved path=%s", p)


def load_baseline(path: str | Path) -> EvalScores:
    p = Path(path)
    if not p.is_file():
        return EvalScores(0.0, 0.0, 0.0, 0.0, 0)
    try:
        data = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        logger.exception("ragas_baseline_load_failed path=%s", p)
        return EvalScores(0.0, 0.0, 0.0, 0.0, 0)
    return EvalScores(
        faithfulness=float(data.get("faithfulness", 0.0)),
        answer_relevance=float(data.get("answer_relevance", 0.0)),
        context_precision=float(data.get("context_precision", 0.0)),
        context_recall=float(data.get("context_recall", 0.0)),
        n_samples=int(data.get("n_samples", 0)),
    )
