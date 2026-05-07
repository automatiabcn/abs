# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-019 — Text2SQL with safety guard-rails (mock + Vanna + Cortex backends)."""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "GeneratedSQL",
    "SafetyError",
    "Text2SQL",
    "assert_safe_sql",
    "close_text2sql",
    "get_text2sql",
]


@dataclass(slots=True)
class GeneratedSQL:
    sql: str
    explanation: str
    parameters: dict[str, str | int | float] | None
    confidence: float
    backend: str


class SafetyError(RuntimeError):
    """Raised when generated SQL violates the read-only contract."""


_FORBIDDEN = (
    "drop", "delete", "insert", "update", "truncate", "alter",
    "create", "grant", "revoke", "attach", "copy", "vacuum",
    "replace", "merge",
)
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN) + r")\b", flags=re.IGNORECASE
)


def assert_safe_sql(sql: str) -> None:
    if not isinstance(sql, str):
        raise SafetyError("sql must be a string")
    text = sql.strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    lowered = text.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SafetyError("only SELECT / WITH (CTE) statements allowed")
    if "--" in text:
        raise SafetyError("inline `--` comments not allowed")
    if ";" in text:
        raise SafetyError("multiple statements not allowed")
    m = _FORBIDDEN_RE.search(lowered)
    if m:
        raise SafetyError(f"forbidden keyword: {m.group(0)}")


class _MockBackend:
    def __init__(self) -> None:
        logger.info("text2sql_mock_init")

    def generate(self, question: str) -> tuple[str, str, float]:
        q = question.lower()
        if "müşteri" in q or "customer" in q:
            return (
                "SELECT id, name, email FROM customers WHERE active = 1 LIMIT 50",
                "mock match: customer",
                0.6,
            )
        if "fatura" in q or "invoice" in q:
            return (
                "SELECT id, customer_id, amount, paid_at FROM invoices "
                "ORDER BY paid_at DESC LIMIT 50",
                "mock match: invoice",
                0.6,
            )
        if "ürün" in q or "product" in q:
            return (
                "SELECT id, name, price FROM products WHERE archived_at IS NULL LIMIT 50",
                "mock match: product",
                0.6,
            )
        if "sipariş" in q or "order" in q:
            return (
                "SELECT id, customer_id, total, created_at FROM orders "
                "ORDER BY created_at DESC LIMIT 50",
                "mock match: order",
                0.6,
            )
        return ("SELECT 1 AS placeholder", "mock match: default", 0.2)


class _VannaBackend:
    def __init__(self, model_name: str, training_data_path: str) -> None:
        try:
            import vanna  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Vanna backend requires `pip install vanna`"
            ) from exc
        self.model_name = model_name
        self.training_data_path = training_data_path
        logger.info("text2sql_vanna_init model=%s", model_name)

    def generate(self, question: str) -> tuple[str, str, float]:
        import vanna

        ctx = vanna.local.LocalContext_OpenAI(model_name=self.model_name)
        sql = ctx.generate_sql(question)
        return sql, "vanna LLM", 0.85


class _CortexFallback:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("cortex backend requires settings.cortex_api_key")
        self.api_key = api_key
        logger.info("text2sql_cortex_init")

    def generate(self, question: str) -> tuple[str, str, float]:
        import httpx

        url = getattr(settings, "cortex_endpoint", "")
        if not url:
            raise RuntimeError("cortex_endpoint not configured")
        r = httpx.post(
            url,
            json={"question": question},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("sql", "SELECT 1"), "cortex fallback", 0.75


class Text2SQL:
    backend: str

    def __init__(self, backend_name: str) -> None:
        self.backend = backend_name.lower()
        self._impl: Any
        if self.backend == "mock":
            self._impl = _MockBackend()
        elif self.backend == "vanna":
            self._impl = _VannaBackend(
                model_name=getattr(settings, "text2sql_model_name", ""),
                training_data_path=getattr(settings, "text2sql_training_path", ""),
            )
        elif self.backend == "cortex":
            self._impl = _CortexFallback(
                api_key=getattr(settings, "cortex_api_key", "") or "",
            )
        else:
            raise ValueError(f"unsupported text2sql backend: {backend_name}")

    def generate(
        self, question: str, *, schema_hint: str | None = None
    ) -> GeneratedSQL:
        sql, explanation, confidence = self._impl.generate(question)
        assert_safe_sql(sql)
        logger.debug(
            "text2sql_generate q_len=%d backend=%s confidence=%.2f",
            len(question),
            self.backend,
            confidence,
        )
        return GeneratedSQL(
            sql=sql,
            explanation=explanation,
            parameters=None,
            confidence=confidence,
            backend=self.backend,
        )

    def explain(self, sql: str) -> str:
        # T-Q01: defense-in-depth — assert_safe_sql() rejects anything that
        # isn't a single SELECT/WITH statement (no `;`, no `--`, no DDL/DML
        # keywords). We re-validate after a strip + length cap to make the
        # f-string interpolation provably safe.
        assert_safe_sql(sql)
        sql_clean = sql.strip().rstrip(";").strip()
        if len(sql_clean) > 4096:
            raise SafetyError("sql exceeds 4 KiB safety cap")
        assert_safe_sql(sql_clean)  # re-check after normalisation
        conn = sqlite3.connect(":memory:")
        try:
            schema_path = getattr(settings, "text2sql_sandbox_schema_path", "")
            if schema_path:
                p = Path(schema_path)
                if p.is_file():
                    conn.executescript(p.read_text(encoding="utf-8"))
            cur = conn.execute(  # nosec B608 — sql twice-validated by assert_safe_sql allowlist
                f"EXPLAIN QUERY PLAN {sql_clean}"
            )
            return "\n".join(" | ".join(map(str, row)) for row in cur.fetchall())
        except sqlite3.Error as exc:
            raise SafetyError(f"sqlite EXPLAIN failed: {exc}") from exc
        finally:
            conn.close()

    def close(self) -> None:
        return None


_singleton: Text2SQL | None = None


def get_text2sql() -> Text2SQL:
    global _singleton
    if _singleton is None:
        backend = getattr(settings, "text2sql_backend", "mock") or "mock"
        _singleton = Text2SQL(backend)
    return _singleton


def close_text2sql() -> None:
    global _singleton
    if _singleton is None:
        return
    try:
        _singleton.close()
    finally:
        _singleton = None
