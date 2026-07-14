"""Two-step plan-first text2SQL tests."""

from __future__ import annotations

from app.erp.two_step_sql import TwoStepSQL, build_plan
from app.erp.vanna_app import Text2SQL


def test_plan_count_intent_for_kac_question() -> None:
    plan = build_plan("Kaç müşteri aktif?")
    assert plan.intent == "count"
    assert plan.entities == ["customers"]
    assert plan.output_columns == ["count(*) AS n"]


def test_plan_sum_intent_for_toplam() -> None:
    plan = build_plan("Geçen ay toplam fatura tutarı")
    assert plan.intent == "sum"
    assert "invoices" in plan.entities
    assert plan.filters


def test_plan_default_list_intent() -> None:
    plan = build_plan("Ürünleri göster")
    assert plan.intent == "list"
    assert "products" in plan.entities


def test_plan_unknown_entity_safe_default() -> None:
    plan = build_plan("Garip soru")
    assert plan.entities == ["unknown"]


def test_two_step_sql_emits_safe_select() -> None:
    out = TwoStepSQL(dispatcher=Text2SQL("mock")).generate("Kaç müşteri var?")
    assert out.sql.upper().startswith("SELECT")
    assert "customers" in out.sql
    assert out.backend == "two_step_via_mock"


def test_two_step_sql_unknown_entity_returns_placeholder() -> None:
    out = TwoStepSQL(dispatcher=Text2SQL("mock")).generate("hava nasıl")
    assert out.sql == "SELECT 1 AS placeholder"
