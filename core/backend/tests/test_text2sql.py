"""Text2SQL safety + dispatcher unit tests."""

from __future__ import annotations

import pytest

from app.config import settings
from app.erp import vanna_app as t2s
from app.erp.vanna_app import SafetyError, Text2SQL


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "text2sql_backend", "mock", raising=False)
    t2s.close_text2sql()
    yield
    t2s.close_text2sql()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select id from customers",
        "WITH t AS (SELECT id FROM x) SELECT * FROM t",
        "  SELECT id FROM customers ;  ",
    ],
)
def test_assert_safe_sql_accepts_select_and_with(sql: str) -> None:
    t2s.assert_safe_sql(sql)


@pytest.mark.parametrize(
    "sql,fragment",
    [
        ("DELETE FROM customers WHERE id = 1", "delete"),
        ("DROP TABLE customers", "drop"),
        ("UPDATE customers SET active = 0", "update"),
        ("INSERT INTO logs VALUES (1)", "insert"),
        ("TRUNCATE TABLE invoices", "truncate"),
        ("ALTER TABLE customers ADD COLUMN x int", "alter"),
        ("SELECT 1; DROP TABLE x", "multiple"),
        ("SELECT 1 -- evil", "comment"),
        ("MERGE INTO t USING s ON ()", "merge"),
        ("VACUUM", "vacuum"),
    ],
)
def test_assert_safe_sql_rejects_dangerous_input(sql: str, fragment: str) -> None:
    with pytest.raises(SafetyError):
        t2s.assert_safe_sql(sql)


def test_generate_returns_select_for_customer_question() -> None:
    g = Text2SQL("mock").generate("müşterileri listele")
    assert g.sql.lower().startswith("select")
    assert "customers" in g.sql.lower()
    assert g.backend == "mock"
    assert 0.0 < g.confidence <= 1.0


def test_generate_default_for_unknown_question() -> None:
    g = Text2SQL("mock").generate("rastgele bir şey")
    assert g.sql == "SELECT 1 AS placeholder"
    assert g.confidence == 0.2


def test_explain_returns_query_plan_string() -> None:
    plan = Text2SQL("mock").explain("SELECT 1 AS x")
    assert isinstance(plan, str)


def test_explain_rejects_unsafe_sql() -> None:
    with pytest.raises(SafetyError):
        Text2SQL("mock").explain("DROP TABLE customers")


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError):
        Text2SQL("nope")


def test_cortex_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cortex_api_key", "", raising=False)
    with pytest.raises(ValueError):
        Text2SQL("cortex")


def test_singleton_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "text2sql_backend", "mock", raising=False)
    t2s.close_text2sql()
    a = t2s.get_text2sql()
    b = t2s.get_text2sql()
    assert a is b
    t2s.close_text2sql()
    c = t2s.get_text2sql()
    assert c is not a


def test_mock_invoice_question_returns_invoices_table() -> None:
    g = Text2SQL("mock").generate("son fatura")
    assert "invoices" in g.sql.lower()


def test_mock_product_question_returns_products_table() -> None:
    g = Text2SQL("mock").generate("aktif ürünler")
    assert "products" in g.sql.lower()


def test_mock_order_question_returns_orders_table() -> None:
    g = Text2SQL("mock").generate("son siparişler")
    assert "orders" in g.sql.lower()
