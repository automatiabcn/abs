# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pipeline × workflow_state durability bağlayıcı (010).

Her pipeline.run() çağrısı:
  ABS_WORKFLOW_DURABLE=1 → start_workflow + record_step + finish_workflow
  ABS_WORKFLOW_DURABLE=0 → no-op (eski davranış, default)

Settings.workflow_durable runtime'da değiştirilebilir (testte monkeypatch ile).
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.workflow.state import finish_workflow, record_step, start_workflow

logger = logging.getLogger(__name__)


class WorkflowSession:
    """Pipeline tarafında kullanılır. workflow_durable off ise tüm metodlar no-op."""

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
