# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer schema — a multi-file, pre-reviewed edit proposal.

The single shape the editor renders: every proposed edit carries a unified diff
*plus* the three signals a raw diff cannot carry: a Senior-Judge quality score,
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
    judge_correctness: Optional[float] = Field(
        default=None,
        description="The model leg: is this a good CHANGE (None if the model did not answer)",
    )
    judge_style: Optional[float] = Field(
        default=None,
        description="The AST fingerprint leg: how well it matches the house style",
    )
    judge_notes: List[str] = Field(
        default_factory=list, description="Teaching notes behind the score"
    )
    blast_radius: Dict[str, Any] = Field(
        default_factory=dict, description="code_graph blast-radius: what this change may affect"
    )
    # None means the model did not say. It defaulted to 0.0, and the panel
    # draws "uncertain" below 0.5 — so silence was rendered as doubt on every
    # edit that omitted the field, which is a warning nobody reads by the time
    # a real one arrives.
    confidence: Optional[float] = Field(
        default=None,
        description="The model's own confidence 0-1, or None if it did not say",
    )
    validation: Dict[str, Any] = Field(
        default_factory=dict, description="patch_engine.validate verdict {valid, stage, reason}"
    )
    dry_run_ok: bool = Field(default=False, description="True if the diff applies cleanly (dry-run)")


class ComposerRun(BaseModel):
    run_id: str
    task: str
    edits: List[ProposedEdit] = Field(default_factory=list)
    summary: str = ""
    risk: str = "low"  # low | medium | high | ungraded (nobody graded it — ask)
    requires_approval: bool = False
    providers_tried: List[str] = Field(default_factory=list)
    provider: str = Field(default="", description="Provider that answered (winner)")
    cost_usd: Optional[float] = Field(
        default=None, description="Estimated generation cost in USD (None if unknown)"
    )
    degraded: bool = False  # the model produced no usable edits
    # Edits the product threw away on the customer's behalf, one sentence each.
    # Until 2026-08-05 a refused truncation left no trace anywhere a customer
    # could see it: the edit vanished, `degraded` stayed False because the
    # model *had* produced edits, and the run arrived carrying the model's own
    # summary of changes that were not in it.
    refused: List[str] = Field(
        default_factory=list,
        description="Proposals refused before grading, and why, in customer-readable words",
    )
    tenant_slug: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
