# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer schema — a multi-file, pre-reviewed edit proposal.

The single shape the editor renders: every proposed edit carries a unified diff
*plus* the three signals Cursor's raw diff cannot: a Senior-Judge quality score,
a deterministic blast-radius ("N files may be affected"), and a dry-run
validation verdict. Risk and the approval gate are derived from those, not from
the model's self-report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProposedEdit(BaseModel):
    path: str = Field(description="Workspace-relative file path")
    unified_diff: str = Field(default="", description="The edit as a unified diff")
    rationale: str = Field(default="", description="Why this change")
    judge_score: Optional[float] = Field(
        default=None, description="Senior-Judge combined score 0-10 (None if not graded)"
    )
    blast_radius: Dict[str, Any] = Field(
        default_factory=dict, description="code_graph blast-radius: what this change may affect"
    )
    confidence: float = Field(default=0.0, description="Model self-report, clamped 0-1")
    validation: Dict[str, Any] = Field(
        default_factory=dict, description="patch_engine.validate verdict {valid, stage, reason}"
    )
    dry_run_ok: bool = Field(default=False, description="True if the diff applies cleanly (dry-run)")


class ComposerRun(BaseModel):
    run_id: str
    task: str
    edits: List[ProposedEdit] = Field(default_factory=list)
    summary: str = ""
    risk: str = "low"  # low | medium | high
    requires_approval: bool = False
    providers_tried: List[str] = Field(default_factory=list)
    degraded: bool = False  # the model produced no usable edits
    tenant_slug: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
