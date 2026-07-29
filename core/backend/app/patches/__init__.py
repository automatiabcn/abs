# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from .engine import (
    ApplyResult,
    DryRunResult,
    Hunk,
    HunkLine,
    ScoreResult,
    ValidationResult,
    apply,
    apply_patch,
    dry_run,
    parse_diff,
    preview_patch,
    score,
    score_patch,
    validate,
)

__all__ = [
    # Back-compat dict API (MCP tools).
    "apply_patch",
    "preview_patch",
    "score_patch",
    # Rich API (Composer).
    "parse_diff",
    "validate",
    "dry_run",
    "apply",
    "score",
    # Dataclasses.
    "Hunk",
    "HunkLine",
    "ValidationResult",
    "DryRunResult",
    "ApplyResult",
    "ScoreResult",
]
