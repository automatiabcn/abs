"""010 — Pipeline × workflow_state durability bağı testleri."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.providers.schemas import ProviderError, ProviderResponse


def _make_resp(
    text: str, model: str = "m", provider: str = "p", elapsed: int = 50
) -> ProviderResponse:
    return ProviderResponse(
        text=text, model=model, provider=provider, elapsed_ms=elapsed
    )


@pytest.fixture
def isolated_workflow_db(monkeypatch, tmp_path: Path):
    """Workflow_state.db'yi tmp dizine yönlendir + her test taze."""
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    yield tmp_path


@pytest.fixture
def fake_providers(monkeypatch):
    """Tüm get_provider çağrıları AsyncMock provider döndürsün."""
    providers: dict[str, object] = {}

    def _set(
        name: str,
        responses: dict[str, ProviderResponse] | None = None,
        raise_for: set[str] | None = None,
        raise_all: bool = False,
    ):
        mock = AsyncMock()

        async def _call(prompt, model=None, **kw):
            if raise_all:
                raise ProviderError("forced fail", provider=name, transient=True)
            if raise_for and model in raise_for:
                raise ProviderError("fake", provider=name, transient=True)
            if responses and model in responses:
                return responses[model]
            return _make_resp(
                f"{name}:{(model or 'default')}", model=model or "?", provider=name
            )

        mock.call = _call
        providers[name] = mock
        return mock

    import app.pipelines.humanize.qual_code_human as qch
    import app.pipelines.humanize.qual_human as qh
    import app.pipelines.humanize.transformer as qtransform
    import app.pipelines.quality.analysis as qa
    import app.pipelines.quality.code as qc
    import app.pipelines.quality.translate as qt
    import app.pipelines.quality.turkish as qtr

    def _get(name):
        return providers.get(name) or _set(name)

    for mod in (qc, qtr, qa, qt, qch):
        monkeypatch.setattr(mod, "get_provider", _get, raising=False)
    # qual_human + transformer humanize_transform üzerinden gider; transform fn'unu mock yerine sahte string döndüren coroutine yap
    if hasattr(qtransform, "get_provider"):
        monkeypatch.setattr(qtransform, "get_provider", _get, raising=False)
    if hasattr(qh, "get_provider"):
        monkeypatch.setattr(qh, "get_provider", _get, raising=False)

    return _set


@pytest.mark.asyncio
async def test_pipeline_no_workflow_when_disabled(
    isolated_workflow_db, fake_providers, monkeypatch
):
    """workflow_durable=False → DB'ye hiçbir kayıt yazılmaz."""
    from app.config import settings
    from app.pipelines.quality.code import QualCodePipeline
    from app.workflow import list_workflows

    monkeypatch.setattr(settings, "workflow_durable", False)
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("def f(): return 1")}
    )
    fake_providers("groq", {"openai/gpt-oss-20b": _make_resp("def f(): return 2")})
    fake_providers("ollama", {"codellama:7b": _make_resp("PASS")})

    result = await QualCodePipeline().run("toy task")

    assert result.error is None
    assert result.workflow_trace_id is None
    assert list_workflows(limit=10) == []  # taze DB boş


@pytest.mark.asyncio
async def test_pipeline_writes_workflow_when_enabled(
    isolated_workflow_db, fake_providers, monkeypatch
):
    """workflow_durable=True → workflow + steps DB'ye yazılır."""
    from app.config import settings
    from app.pipelines.quality.code import QualCodePipeline
    from app.workflow import get_workflow, list_workflows

    monkeypatch.setattr(settings, "workflow_durable", True)
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("def f(): return 1")}
    )
    fake_providers("groq", {"openai/gpt-oss-20b": _make_resp("def f(): return 2")})
    fake_providers("ollama", {"codellama:7b": _make_resp("PASS")})

    result = await QualCodePipeline().run("durable task")

    assert result.workflow_trace_id is not None
    rows = list_workflows(wf_type="qual-code")
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    wf = get_workflow(result.workflow_trace_id)
    assert wf["status"] == "ok"
    assert len(wf["steps"]) >= 1
    step_names = [s["name"] for s in wf["steps"]]
    assert "parallel-drafts" in step_names


@pytest.mark.asyncio
async def test_pipeline_finish_records_status_fail_on_error(
    isolated_workflow_db, fake_providers, monkeypatch
):
    """Tüm provider exception → workflow status 'fail'."""
    from app.config import settings
    from app.pipelines.quality.code import QualCodePipeline
    from app.workflow import get_workflow, list_workflows

    monkeypatch.setattr(settings, "workflow_durable", True)
    fake_providers("cloudflare", raise_all=True)
    fake_providers("groq", raise_all=True)
    fake_providers("ollama", raise_all=True)

    result = await QualCodePipeline().run("force fail")

    assert result.error is not None
    assert result.workflow_trace_id is not None
    rows = list_workflows(wf_type="qual-code")
    assert len(rows) == 1
    assert rows[0]["status"] == "fail"
    wf = get_workflow(result.workflow_trace_id)
    assert wf["status"] == "fail"


@pytest.mark.asyncio
async def test_qual_human_chains_workflow(
    isolated_workflow_db, fake_providers, monkeypatch
):
    """qual_human (parent) + qual-tr (nested) iki ayrı workflow yazar."""
    from app.config import settings
    from app.pipelines.humanize.qual_human import QualHumanPipeline
    from app.workflow import get_workflow, list_workflows

    monkeypatch.setattr(settings, "workflow_durable", True)
    fake_providers(
        "groq", {"qwen/qwen3-32b": _make_resp("Türkçe taslak yeterince uzun")}
    )
    fake_providers("gemini", {"gemini-2.5-flash": _make_resp("Alternatif")})
    fake_providers("ollama", {"aya:8b": _make_resp("TAMAM")})
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("İnsanlaştırılmış")}
    )

    result = await QualHumanPipeline().run("Bir paragraf yaz")

    assert result.workflow_trace_id is not None
    parents = list_workflows(wf_type="qual-human")
    children = list_workflows(wf_type="qual-tr")
    assert len(parents) == 1
    assert len(children) == 1
    parent_wf = get_workflow(result.workflow_trace_id)
    assert parent_wf["status"] == "ok"
    parent_step_names = [s["name"] for s in parent_wf["steps"]]
    assert "qual-tr" in parent_step_names
    assert "humanize-transform" in parent_step_names
