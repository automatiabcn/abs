"""GraphRAG — entity/relation extraction unit tests (no LLM stack required)."""

from __future__ import annotations

import pytest

from app.graph_rag import extract as ex


def test_entity_id_is_deterministic_and_tr_aware() -> None:
    # Same name+type → same id; Turkish characters fold predictably.
    assert ex.entity_id("Ahmet Yılmaz", "Person") == "person:ahmet-yilmaz"
    assert ex.entity_id("ahmet yılmaz", "person") == "person:ahmet-yilmaz"
    assert ex.entity_id("İstanbul Şube", "Location") == "location:istanbul-sube"


def test_norm_type_coerces_synonyms_and_unknowns() -> None:
    assert ex._norm_type("Company") == "Organization"
    assert ex._norm_type("city") == "Location"
    assert ex._norm_type("Wizard") == "Concept"  # unknown → Concept
    assert ex._norm_type(None) == "Concept"


def test_norm_relation_whitelist_fallback() -> None:
    assert ex._norm_relation("works at") == "WORKS_AT"
    assert ex._norm_relation("reports-to") == "REPORTS_TO"
    assert ex._norm_relation("loves") == "RELATED_TO"  # not whitelisted


def test_parse_extraction_happy_path_dedup_and_map() -> None:
    raw = (
        '{"entities":[{"name":"Ahmet","type":"Person"},'
        '{"name":"Ahmet","type":"Person"},'  # duplicate → collapsed
        '{"name":"Automatia","type":"Company"}],'
        '"relations":[{"source":"Ahmet","target":"Automatia","type":"works at"}]}'
    )
    res = ex._parse_extraction(raw)
    assert res is not None
    assert {e.id for e in res.entities} == {"person:ahmet", "organization:automatia"}
    assert len(res.relations) == 1
    rel = res.relations[0]
    assert rel.source_id == "person:ahmet"
    assert rel.target_id == "organization:automatia"
    assert rel.type == "WORKS_AT"


def test_parse_extraction_strips_markdown_fence() -> None:
    raw = '```json\n{"entities":[{"name":"X","type":"Project"}],"relations":[]}\n```'
    res = ex._parse_extraction(raw)
    assert res is not None
    assert res.entities[0].id == "project:x"


def test_parse_extraction_drops_self_and_dangling_relations() -> None:
    raw = (
        '{"entities":[{"name":"A","type":"Person"}],'
        '"relations":['
        '{"source":"A","target":"A","type":"RELATED_TO"},'  # self-loop
        '{"source":"A","target":"Ghost","type":"RELATED_TO"}]}'  # dangling target
    )
    res = ex._parse_extraction(raw)
    assert res is not None
    assert res.relations == []


def test_parse_extraction_invalid_json_returns_none() -> None:
    assert ex._parse_extraction("I could not find any entities, sorry.") is None
    assert ex._parse_extraction("") is None


@pytest.mark.asyncio
async def test_extract_graph_blank_text_skips_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fail(*a, **k):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(ex, "_run_llm", _fail)
    res = await ex.extract_graph("   ", tenant_id="t1")
    assert res.is_empty
    assert called is False


@pytest.mark.asyncio
async def test_extract_graph_uses_llm_output(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(prompt, *, tenant_id, use_cache=True):
        return '{"entities":[{"name":"Ayşe","type":"Person"}],"relations":[]}'

    monkeypatch.setattr(ex, "_run_llm", _fake)
    res = await ex.extract_graph("Ayşe geldi.", tenant_id="t1")
    assert [e.id for e in res.entities] == ["person:ayse"]


@pytest.mark.asyncio
async def test_extract_graph_retries_then_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def _prose(prompt, *, tenant_id, use_cache=True):
        calls["n"] += 1
        return "Sorry, no JSON here."

    monkeypatch.setattr(ex, "_run_llm", _prose)
    res = await ex.extract_graph("some text", tenant_id="t1")
    assert res.is_empty
    assert calls["n"] == 2  # initial + one stricter retry
