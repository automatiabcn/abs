"""Pipeline base abstractions.

Her pipeline BasePipeline'dan türer: async `run(prompt)` → PipelineResult.
Step'ler timing + error birlikte loglanır → panel SSE widget (007+) bu datayı yayar.
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
    workflow_trace_id: Optional[str] = None  # 010 — durable workflow bağlantısı

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
    """Tüm pipeline'ların soyut tabanı."""

    pipeline_type: str = "base"

    @abstractmethod
    async def run(self, prompt: str) -> PipelineResult:
        raise NotImplementedError
