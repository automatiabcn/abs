# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Binds pipeline runs to workflow-state durability.

With ``ABS_WORKFLOW_DURABLE=1`` a pipeline run is checkpointed
(start_workflow / record_step / finish_workflow). Off by default, in which case
every method here is a no-op and no state is written.

The setting is read at call time, so it can change at runtime.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.workflow.state import finish_workflow, record_step, start_workflow

logger = logging.getLogger(__name__)


class WorkflowSession:
    """Pipeline-side handle. Every method is a no-op when durability is off."""

    def __init__(self, wf_type: str, prompt: str):
        self.trace_id: Optional[str] = None
        self.wf_type = wf_type
        if settings.workflow_durable:
            try:
                self.trace_id = start_workflow(wf_type, prompt)
            except Exception as exc:  # pragma: no cover — durability degrade silent
                logger.info("workflow start fail (silent): %s", exc)

    def step(self, name: str, status: str = "ok", result: dict | None = None) -> None:
        if not self.trace_id:
            return
        try:
            record_step(self.trace_id, name, status, result)
        except Exception as exc:  # pragma: no cover
            logger.info("workflow step fail: %s", exc)

    def finish(self, status: str = "ok") -> None:
        if not self.trace_id:
            return
        try:
            finish_workflow(self.trace_id, status)
        except Exception as exc:  # pragma: no cover
            logger.info("workflow finish fail: %s", exc)
