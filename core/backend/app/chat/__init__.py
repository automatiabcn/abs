"""Q12 / Brief 3 — premium chat enhancements.

Modules:
  * `citations` — RAG-grounded chunk retrieval + citation injection helpers.
  * `pipeline_router` — regex-based routing decision (auto / qual_code /
    qual_tr / qual_analysis / race_code / auto_direct).
  * `cost` — per-message USD estimate from provider pricing tables.
"""

from app.chat.citations import (  # noqa: F401
    ChatCitation,
    build_citation_prompt_block,
    retrieve_citations,
)
from app.chat.cost import estimate_call_cost_usd  # noqa: F401
from app.chat.pipeline_router import (  # noqa: F401
    PIPELINE_OPTIONS,
    detect_pipeline,
)

__all__ = [
    "PIPELINE_OPTIONS",
    "ChatCitation",
    "build_citation_prompt_block",
    "detect_pipeline",
    "estimate_call_cost_usd",
    "retrieve_citations",
]
