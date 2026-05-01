"""T-021 — Two-step text2SQL: NL → structured plan → SQL gen.

Plan-first reduces hallucination by forcing the LLM to commit to an
intent/entities/output shape BEFORE it writes SQL. Mock implementation
synthesises a plan from `classify_route`-style hints; real backend will
delegate to an LLM via the same `Text2SQL` dispatcher.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.erp.vanna_app import GeneratedSQL, Text2SQL, assert_safe_sql, get_text2sql

logger = logging.getLogger(__name__)

__all__ = ["QueryPlan", "TwoStepSQL", "build_plan"]


_INTENT_HINTS = {
    "count": ("kaç", "how many", "count", "adet"),
    "sum": ("toplam", "total", "sum", "ciro"),
    "average": ("ortalama", "average", "mean"),
    "list": ("listele", "göster", "list", "show"),
    "trend": ("trend", "geçen ay", "last month", "yıllık"),
}


@dataclass(slots=True)
class QueryPlan:
    intent: str
    entities: list[str]
    output_columns: list[str]
    filters: list[str]
    confidence: float

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "entities": self.entities,
            "output_columns": self.output_columns,
            "filters": self.filters,
            "confidence": self.confidence,
        }


def _detect_intent(question: str) -> tuple[str, float]:
    lowered = question.lower()
    for intent, hints in _INTENT_HINTS.items():
        for h in hints:
            if re.search(rf"\b{re.escape(h)}\b", lowered):
                return intent, 0.7
    return "list", 0.3


def _detect_entities(question: str) -> list[str]:
    lowered = question.lower()
    entities: list[str] = []
    table_hints = {
        "customers": ("müşteri", "customer"),
        "invoices": ("fatura", "invoice"),
        "products": ("ürün", "product"),
        "orders": ("sipariş", "order"),
    }
    for table, hints in table_hints.items():
        if any(h in lowered for h in hints):
            entities.append(table)
    return entities or ["unknown"]


def build_plan(question: str) -> QueryPlan:
    intent, confidence = _detect_intent(question)
    entities = _detect_entities(question)
    output_columns: list[str]
    if intent == "count":
        output_columns = ["count(*) AS n"]
    elif intent == "sum":
        output_columns = ["sum(amount) AS total"]
    elif intent == "average":
        output_columns = ["avg(amount) AS mean"]
    else:
        output_columns = ["id", "*"]
    filters: list[str] = []
    if "geçen ay" in question.lower() or "last month" in question.lower():
        filters.append(
            "created_at >= date('now', 'start of month', '-1 month')"
            " AND created_at < date('now', 'start of month')"
        )
    return QueryPlan(
        intent=intent,
        entities=entities,
        output_columns=output_columns,
        filters=filters,
        confidence=confidence,
    )


def _plan_to_sql(plan: QueryPlan) -> str:
    table = plan.entities[0]
    if table == "unknown":
        return "SELECT 1 AS placeholder"
    cols = ", ".join(plan.output_columns)
    where = (" WHERE " + " AND ".join(plan.filters)) if plan.filters else ""
    return f"SELECT {cols} FROM {table}{where} LIMIT 500"


class TwoStepSQL:
    def __init__(self, *, dispatcher: Text2SQL | None = None) -> None:
        self._dispatcher = dispatcher or get_text2sql()

    def generate(self, question: str) -> GeneratedSQL:
        plan = build_plan(question)
        sql = _plan_to_sql(plan)
        assert_safe_sql(sql)
        logger.debug(
            "two_step_sql intent=%s entities=%s confidence=%.2f",
            plan.intent,
            plan.entities,
            plan.confidence,
        )
        return GeneratedSQL(
            sql=sql,
            explanation=f"plan: {plan.intent} on {plan.entities}",
            parameters=None,
            confidence=plan.confidence,
            backend=f"two_step_via_{self._dispatcher.backend}",
        )
