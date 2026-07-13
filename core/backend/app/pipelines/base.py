# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pipeline base abstractions.

Every pipeline derives from BasePipeline: async `run(prompt)` → PipelineResult.
Each step records its timing alongside its error, so a failed step is still
reported with how long it took; the panel SSE widget renders that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineStep:
    name: str
    model: str = ""
    elapsed_ms: int = 0
    ok: bool = False
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    pipeline_type: str
    steps: List[PipelineStep]
    final_response: str
    total_elapsed_ms: int
    prompt: str
    error: Optional[str] = None
    workflow_trace_id: Optional[str] = None  # link to the durable workflow run

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "pipeline_type": self.pipeline_type,
            "final_response": self.final_response,
            "total_elapsed_ms": self.total_elapsed_ms,
            "error": self.error,
            "steps": [
                {
                    "name": s.name,
                    "model": s.model,
                    "elapsed_ms": s.elapsed_ms,
                    "ok": s.ok,
                    "error": s.error,
                    **({"meta": s.meta} if s.meta else {}),
                }
                for s in self.steps
            ],
        }
        if self.workflow_trace_id:
            out["workflow_trace_id"] = self.workflow_trace_id
        return out


class BasePipeline(ABC):
    """Abstract base for every pipeline."""

    pipeline_type: str = "base"

    @abstractmethod
    async def run(self, prompt: str) -> PipelineResult:
        raise NotImplementedError
