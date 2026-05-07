# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-016 — Structured per-request usage logging (LangFuse-compatible).

Writes newline-delimited JSON to a JSONL file with optional sampling. Future
T-018 will replace the file writer with the LangFuse SDK without changing the
call sites.
"""

from __future__ import annotations

import datetime
import json
import logging
import random
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

LANGFUSE_NAMES = {"rag.ingest", "rag.query", "rag.delete"}

__all__ = [
    "LANGFUSE_NAMES",
    "UsageEvent",
    "UsageLogger",
    "close_usage_logger",
    "get_usage_logger",
    "make_event",
    "utc_iso8601_ms",
]


def utc_iso8601_ms() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(slots=True)
class UsageEvent:
    timestamp: str
    trace_id: str
    name: str
    tenant_id: str | None
    user_subject: str | None
    request_type: str
    status: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    model_version: str
    metadata: dict[str, Any]
    error_code: str | None


class UsageLogger:
    def __init__(
        self,
        *,
        jsonl_path: Path | str | None = None,
        sample_rate: float = 1.0,
    ) -> None:
        self.sample_rate = float(sample_rate)
        if jsonl_path is None:
            jsonl_path = getattr(settings, "usage_log_path", "data/rag_usage.jsonl")
        self.path = Path(jsonl_path)
        self._lock = threading.Lock()
        self._file: Any = None
        self._open()
        logger.info(
            "usage_logger_init path=%s sample_rate=%.3f",
            self.path,
            self.sample_rate,
        )

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8", buffering=1)

    def record(self, event: UsageEvent) -> bool:
        if self.sample_rate < 1.0 and random.random() >= self.sample_rate:
            return False
        try:
            line = json.dumps(
                asdict(event),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            with self._lock:
                if self._file is None:
                    self._open()
                self._file.write(line + "\n")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage_log_write_failed: %s", exc)
            return False

    def close(self) -> None:
        with self._lock:
            if self._file is None:
                return
            try:
                self._file.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("usage_log_close_failed: %s", exc)
            finally:
                self._file = None


_logger_instance: UsageLogger | None = None
_instance_lock = threading.Lock()


def get_usage_logger() -> UsageLogger:
    global _logger_instance
    if _logger_instance is None:
        with _instance_lock:
            if _logger_instance is None:
                _logger_instance = UsageLogger(
                    jsonl_path=getattr(settings, "usage_log_path", None),
                    sample_rate=getattr(settings, "usage_log_sample_rate", 1.0),
                )
    return _logger_instance


def close_usage_logger() -> None:
    global _logger_instance
    if _logger_instance is None:
        return
    with _instance_lock:
        if _logger_instance is None:
            return
        _logger_instance.close()
        _logger_instance = None


def make_event(
    *,
    name: str,
    tenant_id: str | None = None,
    user_subject: str | None = None,
    request_type: str,
    status: str,
    latency_ms: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model_version: str = "",
    metadata: dict[str, Any] | None = None,
    error_code: str | None = None,
    timestamp: str | None = None,
    trace_id: str | None = None,
) -> UsageEvent:
    return UsageEvent(
        timestamp=timestamp or utc_iso8601_ms(),
        trace_id=trace_id or uuid.uuid4().hex,
        name=name,
        tenant_id=tenant_id,
        user_subject=user_subject,
        request_type=request_type,
        status=status,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_version=model_version,
        metadata=dict(metadata or {}),
        error_code=error_code,
    )
