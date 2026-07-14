"""Prompt management tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.observability import prompt_manager as pm


@pytest.fixture()
def store(tmp_path: Path) -> pm.PromptStore:
    return pm.PromptStore(jsonl_path=tmp_path / "prompts.jsonl")


def test_create_first_version_returns_v1(store: pm.PromptStore) -> None:
    p = store.create_version("rag.system", "You are an ABS RAG assistant.")
    assert p.version == 1
    assert store.get("rag.system").version == 1


def test_create_version_increments(store: pm.PromptStore) -> None:
    store.create_version("rag.system", "v1")
    p2 = store.create_version("rag.system", "v2")
    assert p2.version == 2
    assert store.get("rag.system").text == "v2"


def test_rollback_restores_previous_version(store: pm.PromptStore) -> None:
    store.create_version("rag.system", "v1")
    store.create_version("rag.system", "v2")
    rolled = store.rollback("rag.system", to_version=1)
    assert rolled.version == 1
    assert store.get("rag.system").version == 1


def test_rollback_unknown_version_raises(store: pm.PromptStore) -> None:
    store.create_version("rag.system", "v1")
    with pytest.raises(KeyError):
        store.rollback("rag.system", to_version=99)


def test_get_unknown_label_raises(store: pm.PromptStore) -> None:
    with pytest.raises(KeyError):
        store.get("missing.prompt")


def test_list_versions_sorted(store: pm.PromptStore) -> None:
    store.create_version("p", "a")
    store.create_version("p", "b")
    store.create_version("p", "c")
    assert store.list_versions("p") == [1, 2, 3]


def test_persistence_round_trip(tmp_path: Path) -> None:
    a = pm.PromptStore(jsonl_path=tmp_path / "p.jsonl")
    a.create_version("hello", "world", metadata={"author": "abs"})
    a.close()
    b = pm.PromptStore(jsonl_path=tmp_path / "p.jsonl")
    p = b.get("hello")
    assert p.text == "world"
    assert p.metadata == {"author": "abs"}


def test_singleton_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.observability.prompt_manager.settings.prompt_store_path",
        str(tmp_path / "s.jsonl"),
        raising=False,
    )
    pm.close_prompt_store()
    a = pm.get_prompt_store()
    b = pm.get_prompt_store()
    assert a is b
    pm.close_prompt_store()
    c = pm.get_prompt_store()
    assert c is not a
