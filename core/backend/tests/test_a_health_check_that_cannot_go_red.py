# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A health check that cannot go red is not a health check.

Two endpoints report this server's health: `/v1/status` (the public status page)
and `/v1/health/full` (what an operator opens when they suspect something is
wrong). Between them they had four failures that could not be reported:

* **The RAG check was fixed in one file and not the other.** `status_page.py`
  learned to ask whether documents can actually be *searched* — a mock embedding
  backend means every answer is drawn from unrelated chunks. `health_full.py` was
  a copy-paste of the same seven checks and kept the pre-fix body, `import
  chromadb → ok: True`. So the endpoint you reach for during the outage was the
  one still calling it healthy. A check that exists twice gets fixed once.

* **`providers: ok` was hardcoded True**, even with zero providers configured. A
  server that cannot answer a single question reported itself well. The comment
  said no providers at boot is acceptable — true at boot, and untrue for every
  moment after it.

* **The overall verdict counted failures instead of weighing them.** Zero failures
  "ok", one or two "degraded", three or more "down". Four of the seven checks were
  hardcoded to pass, so they padded the denominator and did nothing else — and a
  server with an unreachable database, which can do nothing at all, came out as
  "degraded" because only one box had gone red.

These tests fail if any of that comes back.
"""

from __future__ import annotations

import asyncio

import pytest

from app.api import health_full as hf
from app.api import status_page as sp
from app.config import settings


class _DeadEmbedder:
    """The mock backend, which is what the real outage looked like."""

    backend = "mock"
    semantic = False

    def model_id(self) -> str:
        return "mock:sha256"


def test_the_rag_check_goes_red_when_documents_cannot_be_searched(monkeypatch):
    monkeypatch.setattr(
        "app.rag.embedding_bge.get_embedder", lambda: _DeadEmbedder(), raising=True
    )
    result = sp._check_rag()
    assert result["ok"] is False
    assert "ABS_EMBEDDING_BACKEND" in str(result.get("detail", ""))


def test_both_endpoints_report_the_same_rag_outage(monkeypatch):
    """The drift that made the fix worthless.

    If these two ever disagree, one of them has a private copy again — and it will
    be the copy nobody remembers to fix.
    """
    monkeypatch.setattr(
        "app.rag.embedding_bge.get_embedder", lambda: _DeadEmbedder(), raising=True
    )
    assert sp._check_rag()["ok"] is False
    assert hf._check_rag()["ok"] is False, (
        "/v1/health/full still reports a dead knowledge base as healthy — it has "
        "its own copy of the check again"
    )


def test_the_health_endpoint_does_not_keep_its_own_copy_of_the_rag_check():
    """Belt to the braces above: the same object, not merely the same answer."""
    import inspect

    source = inspect.getsource(hf._check_rag)
    assert "chromadb" not in source or "status_page" in source, (
        "health_full has grown its own RAG check again"
    )


def test_no_providers_configured_is_not_healthy(monkeypatch):
    for attr in (
        "anthropic_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cohere_api_key",
        "cf_account_id",
        "cf_api_token",
    ):
        monkeypatch.setattr(settings, attr, "", raising=False)

    result = sp._check_providers()
    assert result["ok"] is False, (
        "a server with no provider configured cannot answer a question, and said "
        "it was fine"
    )
    assert result["configured_count"] == 0


def test_one_provider_is_enough_to_be_healthy(monkeypatch):
    """Refusing to lie must not turn into crying wolf: the free tier is one key."""
    for attr in (
        "anthropic_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cohere_api_key",
        "cf_account_id",
        "cf_api_token",
    ):
        monkeypatch.setattr(settings, attr, "", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "gsk_x", raising=False)

    result = sp._check_providers()
    assert result["ok"] is True
    assert result["configured_count"] == 1


@pytest.mark.parametrize("dead", ["database", "providers"])
def test_the_status_page_says_down_when_the_server_really_is_down(monkeypatch, dead):
    """One critical failure is an outage, not a degradation.

    Counting failures made this unsayable: the database could be unreachable — no
    login, no chat, no anything — and the page would call it "degraded" because
    only one of seven boxes was red, four of which could not go red at all.
    """
    real_db, real_providers = sp._check_db, sp._check_providers
    monkeypatch.setattr(
        sp,
        "_check_db",
        (lambda: {"name": "database", "ok": False}) if dead == "database" else real_db,
    )
    monkeypatch.setattr(
        sp,
        "_check_providers",
        (lambda: {"name": "providers", "ok": False})
        if dead == "providers"
        else real_providers,
    )

    body = asyncio.run(sp.status_json())

    assert body["overall"] == "down", (
        f"{dead} is unreachable and the status page called it '{body['overall']}'"
    )


def test_a_non_critical_failure_is_a_degradation_not_an_outage(monkeypatch):
    """The other half. A verdict that is always bad is as useless as always good."""
    monkeypatch.setattr(sp, "_check_rag", lambda: {"name": "rag", "ok": False})
    body = asyncio.run(sp.status_json())
    assert body["overall"] == "degraded", (
        "the knowledge base is down, which is bad, and the rest of the product "
        f"still works — that is not an outage, but the page said '{body['overall']}'"
    )


def test_a_healthy_server_still_reads_as_healthy():
    body = asyncio.run(sp.status_json())
    assert body["overall"] in ("ok", "degraded", "down")
    assert isinstance(body["services"], list) and body["services"]
