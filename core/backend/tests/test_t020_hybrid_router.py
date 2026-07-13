"""T-020 — ERP hybrid retrieval classify + merge tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.erp.hybrid_router import classify_route, hybrid_retrieve


def test_classify_sql_only_for_metric_question() -> None:
    decision = classify_route("Geçen ay toplam ciro ne kadar?")
    assert decision.route == "sql"


def test_classify_rag_only_for_explanatory_question() -> None:
    decision = classify_route("Bu ürünün vergi politikasını açıkla")
    assert decision.route == "rag"


def test_classify_hybrid_when_both_signals_present() -> None:
    decision = classify_route("Geçen ay en çok satılan ürünleri özetle")
    assert decision.route == "hybrid"


def test_classify_default_to_rag_on_unknown() -> None:
    decision = classify_route("rastgele bir soru")
    assert decision.route == "rag"
    assert "default" in decision.reasons


def test_hybrid_retrieve_routes_to_rag_only() -> None:
    rag_search = MagicMock(return_value=[{"text": "ans"}])
    text2sql_generate = MagicMock()
    answer = hybrid_retrieve(
        "Bu ürünü açıkla",
        tenant_id="t1",
        rag_search=rag_search,
        text2sql_generate=text2sql_generate,
    )
    assert answer.route == "rag"
    rag_search.assert_called_once()
    text2sql_generate.assert_not_called()
    assert answer.rag_hits == [{"text": "ans"}]
    assert answer.sql_result is None


def test_hybrid_retrieve_routes_to_sql_only() -> None:
    rag_search = MagicMock()
    text2sql_generate = MagicMock(
        return_value=SimpleNamespace(
            sql="SELECT 1", explanation="x", confidence=0.9, backend="mock"
        )
    )
    answer = hybrid_retrieve(
        "Geçen ay toplam fatura",
        tenant_id="t1",
        rag_search=rag_search,
        text2sql_generate=text2sql_generate,
    )
    assert answer.route == "sql"
    rag_search.assert_not_called()
    text2sql_generate.assert_called_once()
    assert answer.sql_result["sql"] == "SELECT 1"


def test_hybrid_retrieve_runs_both_for_hybrid_route() -> None:
    rag_search = MagicMock(return_value=[{"text": "context"}])
    text2sql_generate = MagicMock(
        return_value=SimpleNamespace(
            sql="SELECT count(*) FROM invoices",
            explanation="x",
            confidence=0.7,
            backend="mock",
        )
    )
    answer = hybrid_retrieve(
        "Geçen ay en çok satılan ürünleri özetle",
        tenant_id="t1",
        rag_search=rag_search,
        text2sql_generate=text2sql_generate,
    )
    assert answer.route == "hybrid"
    assert answer.rag_hits
    assert answer.sql_result is not None


def test_hybrid_retrieve_swallows_individual_errors() -> None:
    def boom(*a, **k):  # noqa: ANN001
        raise RuntimeError("downstream down")

    answer = hybrid_retrieve(
        "Bu ürünü açıkla",
        tenant_id="t1",
        rag_search=boom,
        text2sql_generate=MagicMock(),
    )
    assert any("rag_error" in n for n in answer.notes)
    assert answer.rag_hits == []
